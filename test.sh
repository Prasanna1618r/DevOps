pipeline{
    agent none
    stages{
        stage('Build'){
            agent { label 'devopsbuildsrv' }
            tools{
                gradle 'gradle_6_2_1'
            }
            environment{
                ANDROID_SDK_ROOT = "/opt/android-sdk"
                JAVA_HOME = '/usr/lib/jvm/java-11-openjdk-amd64'
                ANDROID_HOME = '/opt/android-sdk'   
                PATH = "${ANDROID_HOME}/build-tools/34.0.0:${env.PATH}"
                ANDROID_ZIPALIGN = "${ANDROID_HOME}/build-tools/34.0.0/zipalign"
            }
            steps{
                
                /*===============================
                 Cleaning workspace before build
                ===============================*/
                script {
                    echo "Cleaning workspace..."
                    deleteDir()
                }
                
                git branch: params.BRANCH, credentialsId: 'gitlab', url: 'https://gitlab.mitsogo.com/android/remotecontrolagent.git'
                withCredentials([string(credentialsId: 'ANDROID_KEY_PASSPHRASE', variable: 'ANDROID_PASSPHRASE'), file(credentialsId: 'JENKINS_AWS_CREDENTIALS', variable: 'AWS_SHARED_CREDENTIALS_FILE'), string(credentialsId: 'jenkins_proxy', variable: 'PROXY')]) {
                    
                    /*=============================
                        Build the Unsigned App
                    =============================*/
                    
                    withGradle{
                        sh 'gradle clean assembleRelease bundleRelease'
                    }
                    
                    /*=============================
                          Signing the App
                    =============================*/
                    
                    sh '''
                        sign_and_align_apk() {
                           unsigned_apk="$1"
                           aligned_apk="$2"
                           signed_apk="$3"
                           app_name="$4"
                           
                           echo "Signing $app_name APK..."
                           
                           "$ANDROID_ZIPALIGN" -v -p 4 "$unsigned_apk" "$aligned_apk"
                           
                           apksigner sign \
                             --ks "$JENKINS_WORKDIR/certificate.jks" \
                             --ks-key-alias "hexnodemdmapp" \
                             --ks-pass pass:$ANDROID_PASSPHRASE \
                             --key-pass pass:$ANDROID_PASSPHRASE \
                             --out "$signed_apk" \
                             "$aligned_apk"
                             
                           if [ $? -ne 0 ]; then
                               echo "critical: failed to sign $app_name APK"
                               exit 1
                           fi
                           echo "$app_name APK signed successfully."
                           
                        }
                        
                        if echo "$APK_ACTION" | grep -iq 'HEXNODEASSIST-APK'; then
                           sign_and_align_apk \
                               "$WORKSPACE/app/build/outputs/apk/remoteControl/release/app-remoteControl-release-unsigned.apk" \
                               "$WORKSPACE/app/build/outputs/apk/remoteControl/release/app-remoteControl-release-aligned.apk" \
                               "$WORKSPACE/app/build/outputs/apk/remoteControl/release/app-remoteControl-release.apk" \
                               "Hexnode Assist"
                        fi
                        if echo "$APK_ACTION" | grep -iq 'HEXNODEREMOTEVIEW'; then
                           sign_and_align_apk \
                               "$WORKSPACE/app/build/outputs/apk/remoteView/release/app-remoteView-release-unsigned.apk" \
                               "$WORKSPACE/app/build/outputs/apk/remoteView/release/app-remoteView-release-aligned.apk" \
                               "$WORKSPACE/app/build/outputs/apk/remoteView/release/app-remoteView-release.apk" \
                               "Hexnode RemoteView"
                        fi
                    '''
                    
                    
                    /*=============================
                          Verify the signing
                    =============================*/
                    
                    sh '''
                            check_apk_signature() {
                               local apk_path="$1"
                               echo "Checking APK signing..." 
                               if [ ! -f "$apk_path" ]; then
                                   echo "critical : APK not found"
                                   exit 1
                               fi
                               if apksigner verify --verbose "$apk_path"; then
                                   echo "info: APK is signed."
                               else
                                   echo "critical: APK is NOT signed."
                                   exit 1
                               fi
                            }
                            
                            if echo "$APK_ACTION" | grep -iq 'HEXNODEASSIST-APK'; then
                               check_apk_signature "$WORKSPACE/app/build/outputs/apk/remoteControl/release/app-remoteControl-release.apk"
                            fi
                            if echo "$APK_ACTION" | grep -iq 'HEXNODEREMOTEVIEW'; then
                               check_apk_signature "$WORKSPACE/app/build/outputs/apk/remoteView/release/app-remoteView-release.apk"
                            fi
                            
                        '''
                        
                    /*====================================
                     Build App and copy the url in url.txt
                    =======================================*/    
                        
                    sh '''#!/bin/bash
                        set +x
                        set +e
    
                        message() {
                            echo "$(date +\'%Y-%m-%d %H:%M:%S\') $(hostname) $1"
                        }
                        
                        S3_URL="s3://testing-hexnode/jenkins/${JOB_NAME}/${BUILD_ID}"
                        assist_version=$(grep -A 5 "remoteControl {" $WORKSPACE/app/build.gradle | grep "versionName" | cut -d \'"\' -f2)
                        remoteview_version=$(grep -A 5 "remoteView {" $WORKSPACE/app/build.gradle | grep "versionName" | cut -d \'"\' -f2)
                        
                        COMMIT_SHA=$(git rev-parse --short HEAD)
                        echo "urls for the build:" > $WORKSPACE/url.txt
                        
                        if echo "$APK_ACTION" | grep -iq 'HEXNODEREMOTEVIEW'; then
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
                        
                        if echo "$APK_ACTION" | grep -iq 'HEXNODEASSIST-APK'; then
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
                        
                        if echo "$APK_ACTION" | grep -iq 'HEXNODEASSIST-AAB'; then
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
                        
                    /*=================================================
                    Send Mail to QA team to test and Approve deployment
                    ==================================================*/    
                        
                    script {
                        emailext(
                            from: "Jenkins Server <jenkins@hexnodemdmnotifications.com>",
                            to: "QA-Leads@mitsogo.com",
                            subject: "Approve Deployment For HEXNODE REMOTEVIEW AND REMOTEASSIST APP",
                            body: """
                                <p>Hi Team,</p>
                                <p>Please check and approve the deployment of HEXNODE REMOTEVIEW AND REMOTEASSIST APP </p>
                                <ul>
                                    <li>Branch Name  - ${params.BRANCH}</li>
                                    <li>RemoteView Application  -  <a href='https://testing-hexnode.s3.eu-central-1.amazonaws.com/jenkins/$JOB_NAME/$BUILD_ID/HexnodeAgentd.pkg'>HexnodeAgentd.pkg</a></li>
                                    <li>RemoteAssist Application -  <a href='https://testing-hexnode.s3.eu-central-1.amazonaws.com/jenkins/${env.JOB_NAME}/${env.BUILD_ID}/HexnodeAgentd.xml'>HexnodeAgentd.xml</a></li>
                                    <li>RemoteAssist AAB -  <a href='https://testing-hexnode.s3.eu-central-1.amazonaws.com/jenkins/${env.JOB_NAME}/${env.BUILD_ID}/HexnodeAgentd.xml'>HexnodeAgentd.xml</a></li>
                                    <li>Jenkins Job  -  <a href='${env.JOB_URL}'>${env.JOB_NAME}</a></li>
                                    <li><b>Approve the deployment</b> <a href='${env.JOB_URL}${env.BUILD_ID}/console'> Here</a></li>
                                </ul><br/>
                                <p>Regards,<br/>Jenkins Pipeline<br/>
                                <a href="https://jenkins.mitsogo.com/">jenkins.mitsogo.com</a></p>
                            """,
                            mimeType: 'text/html'
                        )
                    }
                }
            }
        }
    }
}
