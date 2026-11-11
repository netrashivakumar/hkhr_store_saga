pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    environment {
        REGISTRY = 'ghcr.io'
        OWNER    = 'netrashivakumar'
        SERVICES = 'frontend order-service inventory-service payment-service notification-worker'
    }

    stages {
        stage('Prepare') {
            steps {
                script {
                    // Short commit id, used as the immutable image tag
                    env.TAG = sh(returnStdout: true, script: 'git rev-parse --short=7 HEAD').trim()
                }
                echo "Branch ${env.BRANCH_NAME}, image tag ${env.TAG}"
                sh 'docker version --format "{{.Server.Version}}"'
                sh 'kubectl version --client'
            }
        }

        stage('Test') {
            steps {
                // Runs each service's tests in a throwaway Python 3.12 container.
                // docker cp is used (not a bind mount) because Jenkins itself runs in a container.
                sh '''
                    set -e
                    for svc in $SERVICES; do
                      [ -d "services/$svc/tests" ] || { echo "No tests for $svc, skipping"; continue; }
                      echo "== Testing $svc =="
                      cid=$(docker create python:3.12-slim sh -c 'cd /app && pip install -q -r requirements.txt -r requirements-dev.txt && python -m pytest -q')
                      docker cp "services/$svc" "$cid:/app"
                      docker start -a "$cid" || { docker rm -f "$cid"; exit 1; }
                      docker rm -f "$cid"
                    done
                '''
            }
        }

        stage('Build images') {
            when { anyOf { branch 'dev'; branch 'main' } }
            steps {
                sh '''
                    set -e
                    for svc in $SERVICES; do
                      docker build -t "$REGISTRY/$OWNER/hkhr-$svc:$TAG" "services/$svc"
                    done
                '''
            }
        }

        stage('Push images') {
            when { anyOf { branch 'dev'; branch 'main' } }
            steps {
                withCredentials([usernamePassword(credentialsId: 'ghcr-credentials',
                                                  usernameVariable: 'GHCR_USER',
                                                  passwordVariable: 'GHCR_TOKEN')]) {
                    sh '''
                        set -e
                        echo "$GHCR_TOKEN" | docker login "$REGISTRY" -u "$GHCR_USER" --password-stdin
                        for svc in $SERVICES; do
                          docker push "$REGISTRY/$OWNER/hkhr-$svc:$TAG"
                          if [ "$BRANCH_NAME" = "dev" ]; then
                            docker tag "$REGISTRY/$OWNER/hkhr-$svc:$TAG" "$REGISTRY/$OWNER/hkhr-$svc:dev"
                            docker push "$REGISTRY/$OWNER/hkhr-$svc:dev"
                          fi
                        done
                    '''
                }
            }
        }

        stage('Deploy to staging') {
            when { branch 'dev' }
            steps {
                sh '''
                    set -e
                    # Render the overlay, swap the :dev tag for this build's tag, apply once
                    kubectl kustomize k8s/overlays/staging | sed "s#:dev#:$TAG#" | kubectl apply -f -
                    for svc in $SERVICES; do
                      kubectl -n staging rollout status "deployment/$svc" --timeout=180s
                    done
                    kubectl -n staging get pods
                '''
            }
        }

        stage('Approve production') {
            when { branch 'main' }
            steps {
                timeout(time: 30, unit: 'MINUTES') {
                    input message: "Deploy ${env.TAG} to production?", ok: 'Deploy'
                }
            }
        }

        stage('Deploy to production') {
            when { branch 'main' }
            steps {
                sh '''
                    set -e
                    kubectl kustomize k8s/overlays/production | sed "s#:dev#:$TAG#" | kubectl apply -f -
                    for svc in $SERVICES; do
                      kubectl -n production rollout status "deployment/$svc" --timeout=180s
                    done
                    kubectl -n production get pods
                '''
            }
        }
    }

    post {
        always {
            sh 'docker logout ghcr.io || true'
        }
        success {
            echo "Pipeline finished for ${env.BRANCH_NAME} at ${env.TAG}"
        }
        failure {
            echo "Pipeline failed on ${env.BRANCH_NAME}. Check the stage logs above."
        }
    }
}