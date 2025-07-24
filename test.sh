pipeline{
    agent none
    
    environment{
        JAVA_HOME = "/usr/lib/jvm/java-11-openjdk-amd64"
        BUILD_TIMESTAMP = "${new Date().format('yyyyMMddHHmmss')}"
    }
    tools{
        gradle 'gradle_6_2_1'
    }
    stages{
        stage('Build'){
            agent { label 'devopsbuildsrv' }
            steps{
                withGradle{
                    gradleBuildFile = 'build.gradle'
                    tasks = 'clean assembleRelease bundleRelease'
                }
                git branch: params.BRANCH, credentialsId: 'gitlab', url: 'https://gitlab.mitsogo.com/macosapplication/macosagent.git'
                withCredentials([string(credentialsId: 'ANDROID_KEY_PASSPHRASE', variable: 'ANDROID_PASSPHRASE'), file(credentialsId: 'JENKINS_AWS_CREDENTIALS', variable: 'AWS_SHARED_CREDENTIALS_FILE'), string(credentialsId: 'jenkins_proxy', variable: 'PROXY')]) {
                    step([$class: 'SignApksBuilder', apksToSign: '**/*-unsigned.apk', keyAlias: 'hexnodemdmapp', keyStoreId: '27'])
                    sh '''#!/bin/bash
    
                        message() {
                            echo "$(date +\'%Y-%m-%d %H:%M:%S\') $(hostname) $1"
                        }
                        
                        S3_URL="s3://testing-hexnode/jenkins/${JOB_NAME}/${BUILD_ID}"
                        assist_version=$(grep -A 5 "remoteControl {" $WORKSPACE/app/build.gradle | grep "versionName" | cut -d \'"\' -f2)
                        remoteview_version=$(grep -A 5 "remoteView {" $WORKSPACE/app/build.gradle | grep "versionName" | cut -d \'"\' -f2)
                        
                        COMMIT_SHA=$(git rev-parse --short HEAD)
                        echo "urls for the build:" > $WORKSPACE/url.txt
                        
                        if [[ $APK_ACTION == *"HEXNODEREMOTEVIEW"* ]]; then
                           echo "info: remoteview_version : ${remoteview_version}"
                           aws s3 cp $WORKSPACE/app/build/outputs/apk/remoteView/release/app-remoteView-release.apk "${S3_URL}/${COMMIT_SHA}_hexnoderemoteview_${remoteview_version}.apk" --region eu-central-1 --profile testing-hexnode --no-progress
                           exitcode=$?
                           if [ $exitcode -ne 0 ];then
                                echo "critical:failed copying files to s3"
                                exit 1
                           else
                                echo "info:successfully copied files to s3"
                           fi
                           aws s3 presign "${S3_URL}/${COMMIT_SHA}_hexnoderemoteview_${remoteview_version}.apk" --expires-in 604800 --region eu-central-1 --profile testing-hexnode >> $WORKSPACE/url.txt
                        fi
                        
                        if [[ $APK_ACTION == *"HEXNODEASSIST-APK"* ]]; then
                           echo "info: hexnode assist version: ${assist_version}"
                           aws s3 cp $WORKSPACE/app/build/outputs/apk/remoteControl/release/app-remoteControl-release.apk "${S3_URL}/${COMMIT_SHA}_hexnodeassist_${assist_version}.apk" --region eu-central-1 --profile testing-hexnode --no-progress
                           exitcode=$?
                           if [ $exitcode -ne 0 ];then
                                echo "critical:failed copying files to s3"
                                exit 1
                           else
                                echo "info:successfully copied files to s3"
                           fi
                           aws s3 presign "${S3_URL}/${COMMIT_SHA}_hexnodeassist_${assist_version}.apk" --expires-in 604800 --region eu-central-1 --profile testing-hexnode >> $WORKSPACE/url.txt
                        fi
                        
                        if [[ $APK_ACTION == *"HEXNODEASSIST-AAB"* ]]; then
                            mkdir -p $WORKSPACE/version/remoteassist
                            jarsigner -keystore $JENKINS_WORKDIR/certificate.jks $WORKSPACE/app/build/outputs/bundle/remoteControlRelease/app-remoteControl-release.aab hexnodemdmapp -storepass $ANDROID_PASSPHRASE
                            exitcode=$?
                            if [ $exitcode -ne 0 ]; then
                                echo "critical: failed building aab signing"
                                exit 2
                            else
                                echo "info: successfully signed aab hexnodeassist.aab"
                            fi
                            aws s3 cp $WORKSPACE/app/build/outputs/bundle/remoteControlRelease/app-remoteControl-release.aab "${S3_URL}/${COMMIT_SHA}_hexnodeassist_${assist_version}.aab" --region eu-central-1 --profile testing-hexnode --no-progress
                            exitcode=$?
                            if [ $exitcode -ne 0 ];then
                                 echo "critical:failed copying files to s3"
                                 exit 1
                            else
                                 echo "info:successfully copied files to s3"
                            fi
                            aws s3 presign "${S3_URL}/${COMMIT_SHA}_hexnodeassist_${assist_version}.aab" --expires-in 604800 --region eu-central-1 --profile testing-hexnode >> $WORKSPACE/url.txt
                        fi
                        
                        cat $WORKSPACE/url.txt
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
            agent { label 'devops_job_runner'}
            steps{
                git branch: params.BRANCH, credentialsId: 'gitlab', url: 'https://gitlab.mitsogo.com/macosapplication/macosagent.git'
                withCredentials([file(credentialsId: 'JENKINS_AWS_CREDENTIALS', variable: 'AWS_SHARED_CREDENTIALS_FILE'), string(credentialsId: 'jenkins_proxy', variable: 'PROXY')]) {
                    // sh '''#!/bin/bash
                    //     rm -rf $WORKSPACE/version
                    //     mkdir -p $WORKSPACE/version/remoteview $WORKSPACE/version/remoteassist
                    //     message() {
                    //         echo "$(date +\'%Y-%m-%d %H:%M:%S\') $(hostname) $1"
                    //     }
                    //     export https_proxy=${PROXY}
                    //     BUILD_S3_URL="s3://testing-hexnode/jenkins/$JOB_NAME/$BUILD_ID"
                    //     DEPLOY_S3_URL="s3://downloads.hexnode.com/testing"
                    //     invalidation_apps=()
                    //     [ -z $BUILDJOB_ID ] && message "error: BUILDJOB_ID not provided or empty" && exit 1
                    //     echo "urls for the deploy:" > $WORKSPACE/url.txt
                        
                    //     if [[ $APK_ACTION == *"HEXNODEREMOTEVIEW"* ]]; then
                    //         message "info: deploying hexnoderemoteview.apk from s3"
                        
                    //         file=$(aws s3 ls "${BUILD_S3_URL}/" --profile testing-hexnode --region eu-central-1 | grep "_hexnoderemoteview_.*\\.apk" | awk \'{print $NF}\')
                    //         if [[ -z "$file" ]]; then
                    //             message "error: hexnoderemoteview.apk not found in S3"
                    //             exit 1
                    //         fi
                    //         message "info:Using $file"
                    //         aws s3 cp "${BUILD_S3_URL}/${file}" "$WORKSPACE/version/remoteview/${file}" --profile testing-hexnode --region eu-central-1 --no-progress
                    //         if [ $? -ne 0 ] || ! [ -f "$WORKSPACE/version/remoteview/${file}" ]; then
                    //             message "critical: downloading "{$BUILD_S3_URL}/${file}" failed"
                    //             exit 1
                    //         fi    
                    //         aws s3 cp "$DEPLOY_S3_URL/hexnoderemoteview.apk" "$DEPLOY_S3_URL/version/backups/$JOB_NAME/${BUILD_TIMESTAMP}/" --profile jenkins --region us-east-1 && \\ 
                    //         aws s3 cp "$DEPLOY_S3_URL/hexnoderemoteview.apk.checksum" "$DEPLOY_S3_URL/version/backups/$JOB_NAME/${BUILD_TIMESTAMP}/" --profile jenkins --region us-east-1 && \\
                    //         aws s3 cp "$DEPLOY_S3_URL/hexnoderemoteview.apk" "$DEPLOY_S3_URL/version/backups//$JOB_NAME/${BUILD_TIMESTAMP}/" --profile jenkins --region us-east-1 && \\
                    //         aws s3 cp "$DEPLOY_S3_URL/hexnoderemoteview.apk.checksum" "$DEPLOY_S3_URL/version/backups/$JOB_NAME/${BUILD_TIMESTAMP}/" --profile jenkins --region us-east-1 
                    //         if [ $? -ne 0 ];then
                    //           message "critacal: error backup failed for remoteview"
                    //           exit 1
                    //         fi
                    //         sha256sum $WORKSPACE/version/remoteview/${file} | awk \'{print $1}\' > $WORKSPACE/version/remoteview/${file}.checksum
                    //         aws s3 cp "$WORKSPACE/version/remoteview/${file}" "$DEPLOY_S3_URL/hexnoderemoteview.apk" --profile jenkins --region us-east-1 --acl public-read --no-progress && aws s3 cp "$WORKSPACE/version/remoteview/${file}.checksum" "$DEPLOY_S3_URL/hexnoderemoteview.apk.checksum" --profile jenkins --region us-east-1 --acl public-read --no-progress && \\
                    //         aws s3 cp "$WORKSPACE/version/remoteview/${file}" "$DEPLOY_S3_URL/Hexnoderemoteview.apk" --profile jenkins --region us-east-1 --acl public-read --no-progress && aws s3 cp "$WORKSPACE/version/remoteview/${file}.checksum" "$DEPLOY_S3_URL/Hexnoderemoteview.apk.checksum" --profile jenkins --region us-east-1 --acl public-read --no-progress && \\
                    //         aws s3 cp "$WORKSPACE/version/remoteview/${file}" "$DEPLOY_S3_URL/version/remoteview/" --profile jenkins --region us-east-1  --no-progress && aws s3 cp "$WORKSPACE/version/remoteview/${file}.checksum" "$DEPLOY_S3_URL/version/remoteview/" --profile jenkins --region us-east-1  --no-progress
                    //         exitcode=$?
                    //         if [ $exitcode -eq 0 ];then
                    //           message "info:successfully uploaded files to s3 https://downloads.hexnode.com/hexnoderemoteview.apk bucket"
                    //           invalidation_apps+=("/hexnoderemoteview.apk" "/hexnoderemoteview.apk.checksum" "/Hexnoderemoteview.apk" "/Hexnoderemoteview.apk.checksum")   
                    //           echo "hexnoderemoteview URLs:" >> "$WORKSPACE/url.txt"
                    //           echo "https://downloads.hexnode.com/hexnoderemoteview.apk" >> "$WORKSPACE/url.txt"
                    //           echo "https://downloads.hexnode.com/hexnoderemoteview.apk.checksum" >> "$WORKSPACE/url.txt"
                    //           echo "https://downloads.hexnode.com/Hexnoderemoteview.apk" >> "$WORKSPACE/url.txt"
                    //           echo "https://downloads.hexnode.com/Hexnoderemoteview.apk.checksum" >> "$WORKSPACE/url.txt"
                    //         else
                    //           message "critical: upload file ${file} to s3 https://downloads.hexnode.com/hexnoderemoteview.apk bucket failed"
                    //           exit 1
                    //         fi
                    //     fi
                         
                    //     if [[ $APK_ACTION == *"HEXNODEASSIST-APK"* ]]; then
                    //         message "info: downloading hexnodeassist.apk"
                    //         file=$(aws s3 ls "${BUILD_S3_URL}/" --profile testing-hexnode --region eu-central-1 | grep "_hexnodeassist_.*\\.apk" | awk \'{print $NF}\')
                    //         if [[ -z "$file" ]]; then
                    //             message "error: hexnodeassist.apk not found in S3"
                    //             exit 1
                    //         fi
                    //         message "info:Using $file"
                    //         aws s3 cp "${BUILD_S3_URL}/${file}" "$WORKSPACE/version/remoteassist/${file}" --profile testing-hexnode --region eu-central-1 --no-progress
                    //         if [ $? -ne 0 ] || ! [ -f "$WORKSPACE/version/remoteassist/${file}" ]; then
                    //             message "critical: downloading "{$BUILD_S3_URL}/${file}" failed"
                    //             exit 1
                    //         fi 
                            
                    //         aws s3 cp "$DEPLOY_S3_URL/hexnodeassist.apk" "$DEPLOY_S3_URL/version/backups/$JOB_NAME/${BUILD_TIMESTAMP}/" --profile jenkins --region us-east-1 && \\ 
                    //         aws s3 cp "$DEPLOY_S3_URL/hexnodeassist.apk.checksum" "$DEPLOY_S3_URL/version/backups/$JOB_NAME/${BUILD_TIMESTAMP}/" --profile jenkins --region us-east-1 && \\
                    //         aws s3 cp "$DEPLOY_S3_URL/Hexnodeassist.apk" "$DEPLOY_S3_URL/version/backups/$JOB_NAME/${BUILD_TIMESTAMP}/" --profile jenkins --region us-east-1 && \\
                    //         aws s3 cp "$DEPLOY_S3_URL/Hexnodeassist.apk.checksum" "$DEPLOY_S3_URL/version/backups/$JOB_NAME/${BUILD_TIMESTAMP}/" --profile jenkins --region us-east-1 
                    //         if [ $? -ne 0 ];then
                    //           message "critacal: error backup failed for hexnodeassist.apk"
                    //           exit 1
                    //         fi
                    //         sha256sum $WORKSPACE/version/remoteassist/${file} | awk \'{print $1}\' > $WORKSPACE/version/remoteassist/${file}.checksum
                    //         aws s3 cp "$WORKSPACE/version/remoteassist/${file}" "$DEPLOY_S3_URL/hexnodeassist.apk" --profile jenkins --region us-east-1 --acl public-read --no-progress && aws s3 cp "$WORKSPACE/version/remoteassist/${file}.checksum" "$DEPLOY_S3_URL/hexnodeassist.apk.checksum" --profile jenkins --region us-east-1 --acl public-read --no-progress && \\
                    //         aws s3 cp "$WORKSPACE/version/remoteassist/${file}" "$DEPLOY_S3_URL/Hexnodeassist.apk" --profile jenkins --region us-east-1 --acl public-read --no-progress && aws s3 cp "$WORKSPACE/version/remoteassist/${file}.checksum" "$DEPLOY_S3_URL/Hexnodeassist.apk.checksum" --profile jenkins --region us-east-1 --acl public-read --no-progress && \\
                    //         aws s3 cp "$WORKSPACE/version/remoteassist/${file}" "$DEPLOY_S3_URL/version/remoteassist/" --profile jenkins --region us-east-1  --no-progress && aws s3 cp "$WORKSPACE/version/remoteassist/${file}.checksum" "$DEPLOY_S3_URL/version/remoteassist/" --profile jenkins --region us-east-1  --no-progress
                    //         exitcode=$?
                    //         if [ $exitcode -eq 0 ];then
                    //           message "info:successfully uploaded files to s3 https://downloads.hexnode.com/hexnodeassist.apk bucket"
                    //           invalidation_apps+=("/hexnodeassist.apk" "/hexnodeassist.apk.checksum" "/Hexnodeassist.apk" "/Hexnodeassist.apk.checksum")
                    //           echo "hexnodeassist APK URLs:" >> "$WORKSPACE/url.txt"
                    //           echo "https://downloads.hexnode.com/hexnodeassist.apk" >> "$WORKSPACE/url.txt"
                    //           echo "https://downloads.hexnode.com/hexnodeassist.apk.checksum" >> "$WORKSPACE/url.txt"
                    //         else
                    //           message "critical: upload file ${file} to s3 https://downloads.hexnode.com/hexnodeassist.apk bucket failed"
                    //           exit 1
                    //         fi
                    //     fi
                         
                    //     if [[ $APK_ACTION == *"HEXNODEASSIST-AAB"* ]]; then
                    //         message "info: downloading hexnodeassist.aab"
                    //         file=$(aws s3 ls "${BUILD_S3_URL}/" --profile testing-hexnode --region eu-central-1 | grep "_hexnodeassist_.*\\.aab" | awk \'{print $NF}\')
                    //         if [[ -z "$file" ]]; then
                    //             message "error: hexnodeassist.aab not found in S3"
                    //             exit 1
                    //         fi
                    //         aws s3 cp "$DEPLOY_S3_URL/hexnodeassist.aab" "$DEPLOY_S3_URL/version/backups/$JOB_NAME/${BUILD_TIMESTAMP}/" --profile jenkins --region us-east-1 && \\ 
                    //         aws s3 cp "$DEPLOY_S3_URL/hexnodeassist.aab.checksum" "$DEPLOY_S3_URL/version/backups/$JOB_NAME/${BUILD_TIMESTAMP}/" --profile jenkins --region us-east-1 
                    //         if [ $? -ne 0 ];then
                    //           message "critical: error backup failed for hexnodeassist.aab"
                    //           exit 1
                    //         fi
                    //         message "info:Using $file"
                    //         aws s3 cp "${BUILD_S3_URL}/${file}" "$WORKSPACE/version/remoteassist/${file}" --profile testing-hexnode --region eu-central-1 --no-progress
                    //         if [ $? -ne 0 ] || ! [ -f "$WORKSPACE/version/remoteassist/${file}" ]; then
                    //             message "critical: downloading "{$BUILD_S3_URL}/${file}" failed"
                    //             exit 1
                    //         fi 
                            
                    //         sha256sum $WORKSPACE/version/remoteassist/${file} | awk \'{print $1}\' > $WORKSPACE/version/remoteassist/${file}.checksum
                    //         aws s3 cp "$WORKSPACE/version/remoteassist/${file}" "$DEPLOY_S3_URL/hexnodeassist.aab" --profile jenkins --region us-east-1  --no-progress && aws s3 cp "$WORKSPACE/version/remoteassist/${file}.checksum" "$DEPLOY_S3_URL/hexnodeassist.aab.checksum" --profile jenkins --region us-east-1  --no-progress && \\
                    //         aws s3 cp "$WORKSPACE/version/remoteassist/${file}" "$DEPLOY_S3_URL/version/remoteassist/" --profile jenkins --region us-east-1 --no-progress && aws s3 cp "$WORKSPACE/version/remoteassist/${file}.checksum" "$DEPLOY_S3_URL/version/remoteassist/" --profile jenkins --region us-east-1 --no-progress
                    //         exitcode=$?
                    //         if [ $exitcode -eq 0 ];then
                    //           message "info:successfully uploaded files to s3 https://downloads.hexnode.com/hexnodeassist.aab bucket"
                    //           echo "hexnodeassist.aab presigned URL: $(aws s3 presign s3://downloads.hexnode.com/hexnodeassist.aab --expires-in 259200 --region us-east-1 --profile jenkins)" >> "$WORKSPACE/url.txt"
                    //         else
                    //           message "critical: upload file ${file} to s3 https://downloads.hexnode.com/hexnodeassist.aab bucket failed"
                    //           exit 1
                    //         fi
                    //     fi
                    //     export https_proxy=${PROXY}
                    //     cat $WORKSPACE/url.txt
                    //     '''
                }
            }
        }
    }
}
