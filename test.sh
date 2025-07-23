pipeline {
    agent none
    
    environment {
        DEVELOPER_DIR = "/Applications/Xcode_13.3.app/Contents/Developer"
        WORKSPACE_DIR = "${env.WORKSPACE}"
        SCHEME = "hexnodeagent"
        CONFIGURATION = "Release"
        EXPORT_OPTIONS_PLIST = "${env.WORKSPACE}/ExportOptions.plist"
        ARCHIVE_PATH = "${env.WORKSPACE}/build/${SCHEME}.xcarchive"
        IPA_OUTPUT_PATH = "${env.WORKSPACE}/build"
        AWS_SHARED_CREDENTIALS_FILE = ''
        BUILD_TIMESTAMP = "${new Date().format('yyyyMMddHHmmss')}"
    }

    stages {
        stage('Build App') {
            agent { label 'mac_mini_kochi' }

            steps {

                /*===============================
                 Cleaning workspace before build
                ===============================*/
                script {
                    echo "Cleaning workspace..."
                    deleteDir()
                }
                git branch: params.BRANCH, credentialsId: 'gitlab', url: 'https://gitlab.mitsogo.com/macosapplication/macosagent.git'


                /*=============================
                 Set App version and Build App
                =============================*/
                sh '''
                    #!/bin/bash
                    set -xe
                    message() { echo -e "\\n[$(date +\'%Y-%m-%d %H:%M:%S\') $NODE_NAME] $1"; }

                    info_file="hexnodeagentd/Info.plist"
                    export CFBundleShortVersionString=$(plutil -extract CFBundleShortVersionString xml1 -o - "$info_file"|sed -n \'s/.*<string>\\(.*\\)<\\/string>.*/\\1/p\')
                    export CFBundleVersion=$(plutil -extract CFBundleVersion xml1 -o - "$info_file"|sed -n \'s/.*<string>\\(.*\\)<\\/string>.*/\\1/p\')
                    
                    echo CFBundleVersion=$CFBundleVersion
                    echo CFBundleShortVersionString=$CFBundleShortVersionString
                    [ -z $CFBundleVersion ] && exit 1
                    [ -z $CFBundleShortVersionString ] && exit 1
                    sleep 5

                    rm -rf /Users/mitsogodevops/Library/Developer/Xcode/DerivedData/hexnodeagentd*
                    xcode=/Applications/Xcode_13.3.app/Contents/Developer/usr/bin/xcodebuild
                    export DEVELOPER_DIR=/Applications/Xcode_13.3.app/Contents/Developer

                    /usr/bin/agvtool mvers -terse1
                    /usr/bin/agvtool vers -terse
                    /usr/bin/agvtool new-marketing-version $CFBundleShortVersionString
                    /usr/bin/agvtool new-version -all $CFBundleVersion
                    /usr/bin/security find-certificate -a -c BX6L6CPUN8 -Z | grep ^SHA-1
                    $xcode -showsdks
                    $xcode -list
                    $xcode -version
                    /usr/bin/security find-identity -p codesigning -v
                    
                    echo "Building App..."
                    $xcode -scheme hexnodeagent -configuration Release clean build BUILD_DIR=${WORKSPACE}/build DEVELOPMENT_TEAM=BX6L6CPUN8 -allowProvisioningUpdates
                '''
            
                /*=====================================================
                 pkgbuild, productbuild, notarization and upload to s3
                =====================================================*/
                withCredentials([file(credentialsId: 'JENKINS_AWS_CREDENTIALS', variable: 'AWS_SHARED_CREDENTIALS_FILE')]) {
                sh '''
                    #!/bin/bash
                    set +x
                    set +e
                    
                    message() { echo -e "\\n[$(date +\'%Y-%m-%d %H:%M:%S\') $NODE_NAME] $1"; }
                    
                    notarization(){
                        local file="$1"
                        message "info:notarizing $file"
                        xcrun notarytool submit "$file" -p notarizationkey --wait
                        [ $? -ne 0 ] && message "error:while notarizing $file" && exit 1
                        
                        file=$(echo "$file"| sed \'s/\\.zip$//\') 
                        message "info:stapling $file"
                        xcrun stapler staple "$file"
                        [ $? -ne 0 ] && message "error:while stapling $file" && exit 1
                        
                        message "info:verifying notarization"
                        spctl --assess -vvv --type install "$file"
                        [ $? -ne 0 ] && message "error:while verifying notarization" && exit 1
                        [[ "$2" == "zip" ]] && message "info:removing zip file" && rm -rf "$file.zip"
                    }
                    export PYTHONWARNINGS=ignore::UserWarning

                    info_file="hexnodeagentd/Info.plist"
                    export CFBundleShortVersionString=$(plutil -extract CFBundleShortVersionString xml1 -o - "$info_file"|sed -n \'s/.*<string>\\(.*\\)<\\/string>.*/\\1/p\')
                    export CFBundleVersion=$(plutil -extract CFBundleVersion xml1 -o - "$info_file"|sed -n \'s/.*<string>\\(.*\\)<\\/string>.*/\\1/p\')
                    
                    COMMIT_SHA=$(git rev-parse --short HEAD)
                    [ $? -ne 0 ] && message "error:while fetching commit SHA" && exit 1
                    message "info:COMMIT_SHA - $COMMIT_SHA"
                    
                    message "info:cleaning and setting up workspace"
                    rm -rf __MACOSX url.txt pkgBuildForAgentd
                    cp -a /Users/mitsogodevops/pkgBuildForAgentd .
                    mkdir -p $WORKSPACE/outputs/$BUILD_TIMESTAMP
                    rm -rf pkgBuildForAgentd/pkgbuild/Root/Library/Application\\ Support/HexnodeMDM/Hexnode\\ UEM\\ Helper.app
                    
                    message "info:notarizing Hexnode\\ UEM\\ Helper.app"
                    cd $WORKSPACE/build/Release/
                    zip -r -y Hexnode\\ UEM\\ Helper.app.zip Hexnode\\ UEM\\ Helper.app
                    notarization "Hexnode UEM Helper.app.zip" "zip"
                    cd $WORKSPACE
                    
                    mv $WORKSPACE/build/Release/hexnodeagentd $WORKSPACE/pkgBuildForAgentd/pkgbuild/Root/Library/Application\\ Support/HexnodeMDM/hexnodeagentd 
                    mv $WORKSPACE/build/Release/Hexnode\\ UEM\\ Helper.app $WORKSPACE/pkgBuildForAgentd/pkgbuild/Root/Library/Application\\ Support/HexnodeMDM/
                    
                    message "info:running package build for the file"
                    pkgbuild --root pkgBuildForAgentd/pkgbuild/Root --identifier com.hexnode.hexnodeagentd --install-location / --version ${CFBundleShortVersionString} --scripts pkgBuildForAgentd/Scripts --sign \'Developer ID Installer: Mitsogo Inc (BX6L6CPUN8)\' --component-plist pkgBuildForAgentd/pkgbuild/component.plist  pkgBuildForAgentd/Build/hexnodeagentd.pkg
                    [ $? -ne 0 ] && message "error:during package build" && exit 1
                    
                    message "info:running product build"
                    productbuild --resources pkgBuildForAgentd/productbuild/Resources --package pkgBuildForAgentd/Build/hexnodeagentd.pkg --product pkgBuildForAgentd/productbuild/Requirements.plist --sign \'Developer ID Installer: Mitsogo Inc (BX6L6CPUN8)\' pkgBuildForAgentd/DistributionPkg/hexnodeagentd.pkg
                    [ $? -ne 0 ] && message "error:during product build" && exit 1
                    
                    message "info:notarizing hexnodeagentd.pkg"
                    notarization "pkgBuildForAgentd/DistributionPkg/hexnodeagentd.pkg"
                    
                    mv pkgBuildForAgentd/DistributionPkg/hexnodeagentd.pkg $WORKSPACE/outputs/$BUILD_TIMESTAMP/
                    rm -rf $WORKSPACE/build/Release/ 
                    cd $WORKSPACE/outputs/${BUILD_TIMESTAMP}/
                    
                    S3_PATH="s3://testing-hexnode/jenkins/$JOB_NAME/$BUILD_ID"
                    message "info:uploading hexnodeagentd.pkg and files to S3"
                    sha256sum hexnodeagentd.pkg|awk \'{print $1}\' > hexnodeagentd.pkg.checksum 

                    aws s3 cp hexnodeagentd.pkg ${S3_PATH}/HexnodeAgentd.pkg --profile testing-hexnode --no-progress  --acl public-read && 
                    aws s3 cp hexnodeagentd.pkg ${S3_PATH}/${COMMIT_SHA}_HexnodeAgentd-$CFBundleShortVersionString.pkg --profile testing-hexnode --acl public-read --no-progress &&
                    aws s3 cp hexnodeagentd.pkg.checksum ${S3_PATH}/HexnodeAgentd.pkg.checksum --profile testing-hexnode --no-progress
                    [ $? -ne 0 ] && message "error:while uploading hexnodeagentd.pkg to S3" && exit 1

                    message "info:s3 url for HexnodeAgentd.pkg"
                    echo "https://testing-hexnode.s3.eu-central-1.amazonaws.com/jenkins/$JOB_NAME/$BUILD_ID/HexnodeAgentd.pkg" > "$WORKSPACE/url.txt"

                    message "info:app urls"
                    cat $WORKSPACE/url.txt
                '''

                /*=========================
                 Create test manifest file
                =========================*/
                script {
                    build job: 'DEPLOY_MACOS/DEPLOY_MACOS_CREATE_MANIFESTURL_AGENTD', parameters: [
                        string(name: 'PKG_URL', value: "testing-hexnode/jenkins/${env.JOB_NAME}/${env.BUILD_ID}/HexnodeAgentd.pkg"),
                        string(name: 'MANIFEST_URL', value: "testing-hexnode/jenkins/${env.JOB_NAME}/${env.BUILD_ID}/HexnodeAgentd.xml")
                    ]
                }
                sh '''
                    #!/bin/bash
                    set +xe
                    message() { echo -e "\\n[$(date +\'%Y-%m-%d %H:%M:%S\') $NODE_NAME] $1"; }
                    message "info:manifest url"
                    echo "https://testing-hexnode.s3.eu-central-1.amazonaws.com/jenkins/${JOB_NAME}/${BUILD_ID}/HexnodeAgentd.xml"
                '''
                }
            }
        }

        stage('Approve Deployment'){
            agent none
            steps {
                input(
                    id: 'qa-approval',
                    message: "QA Approve deployment for branch '${params.BRANCH}'?",
                    ok: "Approve",
                    cancel: 'Cancel',
                    submitter: 'jibin@mitsogo.com'
                )
                input(
                    id: 'devops-approval',
                    message: "DevOps Approve deployment for branch '${params.BRANCH}'?",
                    ok: "Approve",
                    cancel: 'Cancel',
                    submitter: 'alfin.antony@mitsogo.com,vivin@mitsogo.com'
                )
            }
        }

        stage('Deploy'){
            agent{ label 'devops_job_runner'}
            steps{
                sh '''
                    #!/bin/bash
                    set +xe
                    message() { echo -e "\\n[$(date +\'%Y-%m-%d %H:%M:%S\') $NODE_NAME] $1"; }
                    message "info:manifest url"
                    echo "https://downloads.hexnode.com/macos-manifesturl/v2/HexnodeAgentd.xml"
                '''
            }
        }
    }
    post {
        always {
            script {
                node('devops_job_runner') {
                    echo 'Cleaning workspace...'
                    deleteDir()
                }
                node('mac_mini_kochi') {
                    echo 'Cleaning workspace...'
                    deleteDir()
                }
            }
        }
    }
}
