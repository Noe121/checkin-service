pipeline {
    agent any

    environment {
        DOCKER_IMAGE = "nilbx/checkin-service"
        DOCKER_TAG = "${env.BUILD_NUMBER}"
        AWS_REGION = "us-east-1"
        ECR_REGISTRY = credentials('ecr-registry-url')
        DB_HOST = "localhost"
        DB_PORT = "3306"
        DB_USER = "root"
        DB_PASSWORD = credentials('db-password')
        DB_NAME = "nilbx_db"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                sh 'git rev-parse --short HEAD > .git/commit-id'
                script {
                    env.GIT_COMMIT_SHORT = readFile('.git/commit-id').trim()
                }
            }
        }

        stage('Setup Python Environment') {
            steps {
                sh '''
                    python3 -m venv .venv
                    . .venv/bin/activate
                    pip install --upgrade pip
                    pip install -r requirements.txt
                '''
            }
        }

        stage('Lint & Type Check') {
            steps {
                sh '''
                    . .venv/bin/activate
                    # Run linting if configured
                    # flake8 src/ || true
                    # mypy src/ || true
                '''
            }
        }

        stage('Unit Tests') {
            steps {
                sh '''
                    . .venv/bin/activate
                    chmod +x run_tests.sh
                    ./run_tests.sh
                '''
            }
            post {
                always {
                    junit '**/test-results/*.xml' allowEmptyResults: true
                }
            }
        }

        stage('Build Docker Image') {
            steps {
                script {
                    docker.build("${DOCKER_IMAGE}:${DOCKER_TAG}")
                    docker.build("${DOCKER_IMAGE}:latest")
                }
            }
        }

        stage('Start Test Environment') {
            steps {
                sh '''
                    # Start service and database in background
                    docker-compose up -d

                    # Wait for service to be ready
                    echo "Waiting for service to start..."
                    sleep 10

                    # Check if containers are running
                    docker-compose ps
                '''
            }
        }

        stage('Smoke Tests') {
            steps {
                sh '''
                    chmod +x smoke_checkin.sh

                    # Run smoke tests against local instance
                    BASE_URL=http://localhost:8006 ./smoke_checkin.sh
                '''
            }
        }

        stage('Push to ECR') {
            when {
                anyOf {
                    branch 'main'
                    branch 'develop'
                }
            }
            steps {
                script {
                    docker.withRegistry("https://${ECR_REGISTRY}", 'ecr:us-east-1:aws-credentials') {
                        docker.image("${DOCKER_IMAGE}:${DOCKER_TAG}").push()
                        docker.image("${DOCKER_IMAGE}:${GIT_COMMIT_SHORT}").push()

                        if (env.BRANCH_NAME == 'main') {
                            docker.image("${DOCKER_IMAGE}:latest").push()
                        }
                    }
                }
            }
        }

        stage('Deploy to Dev') {
            when {
                branch 'develop'
            }
            steps {
                sh '''
                    # Update ECS service or trigger deployment
                    aws ecs update-service \
                        --cluster nilbx-dev-cluster \
                        --service checkin-service \
                        --force-new-deployment \
                        --region ${AWS_REGION}
                '''
            }
        }

        stage('Deploy to Production') {
            when {
                branch 'main'
            }
            steps {
                input message: 'Deploy to Production?', ok: 'Deploy'

                sh '''
                    # Update ECS service for production
                    aws ecs update-service \
                        --cluster nilbx-prod-cluster \
                        --service checkin-service \
                        --force-new-deployment \
                        --region ${AWS_REGION}
                '''
            }
        }
    }

    post {
        always {
            sh 'docker-compose down -v || true'
            cleanWs()
        }
        success {
            echo 'Pipeline succeeded!'
        }
        failure {
            echo 'Pipeline failed!'
            // Add notifications here (Slack, email, etc.)
        }
    }
}
