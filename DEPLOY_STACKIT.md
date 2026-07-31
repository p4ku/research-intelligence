# Deploying Research Intelligence to STACKIT Cloud Foundry

This guide explains how to deploy the applications in this repository (`backend`, `frontend`, `celery_worker`, `celery_beat`) to **STACKIT Cloud Foundry**.

---

## 🏗️ How Docker-Compose Maps to STACKIT Cloud Foundry

When deploying to production/staging, the local services in `docker-compose.yml` are replaced with managed STACKIT cloud resources and standalone Cloud Foundry application instances (containers):

| Local Service | STACKIT / Cloud Foundry Equivalent | Description |
| :--- | :--- | :--- |
| `db` (Postgres + `pgvector`) | **STACKIT Managed PostgreSQL Flex** | Relational DB with native vector similarity search. |
| `redis` | **STACKIT Managed Redis** | Task queue broker for Celery and application cache. |
| `minio` (S3 replacement) | **STACKIT Object Storage** | S3-compatible bucket storing PDFs and parsed Markdowns. |
| `backend` (Django REST API) | **Cloud Foundry App (`ri-backend`)** | Django running in a container, exposed via STACKIT routes. |
| `celery_worker` | **Cloud Foundry App (`ri-celery-worker`)** | Background task processing engine (no external routes). |
| `celery_beat` | **Cloud Foundry App (`ri-celery-beat`)** | Periodic scheduler trigger (strictly 1 instance, no routes). |
| `frontend` (Next.js Dashboard) | **Cloud Foundry App (`ri-frontend`)** | Next.js static compile served by Nginx container. |

---

## 🛠️ Step 1: Prerequisites & Installation

To deploy and manage the applications, you must install the **Cloud Foundry CLI**:

- **macOS**:
  ```bash
  brew tap cloudfoundry/tap
  brew install cf-cli@8
  ```
- **Windows (Scoop)**:
  ```powershell
  scoop install cf-cli
  ```
- **Linux (Ubuntu/Debian)**:
  ```bash
  wget -q -O - https://packages.cloudfoundry.org/debian/cli.cloudfoundry.org.key | sudo apt-key add -
  echo "deb https://packages.cloudfoundry.org/debian stable main" | sudo tee /etc/apt/sources.list.d/cloudfoundry-cli.list
  sudo apt-get update
  sudo apt-get install cf8-cli
  ```

---

## 🚀 Step 2: Deployment Steps

### 1. Authenticate with STACKIT Cloud Foundry
Log in and target your specific environment space (`development`, `staging`, or `production`):
```bash
cf login -a https://api.apps.eu01.onstackit.cloud -u YOUR_EMAIL_ADDRESS
cf target -o schwarz-dev-org -s development
```

### 2. Verify Infrastructure Services
Ensure the database, redis, and object storage have been provisioned by the infrastructure team (using Terraform). List the active service bindings in your space:
```bash
cf services
```
*You must see `ri-dev-postgres-service`, `ri-dev-redis-service`, and `ri-dev-storage-service` in the output.*

### 3. Build & Push the Frontend Docker Image
Because the frontend runs as an Nginx proxy container serving static Next.js assets, you must build the image and push it to the STACKIT Container Registry:

```bash
# 1. Log in to the STACKIT Registry
docker login registry.eu01.onstackit.cloud -u YOUR_REGISTRY_USER -p YOUR_REGISTRY_PASSWORD

# 2. Build the Docker image (Nginx + static React files)
docker build -t registry.eu01.onstackit.cloud/research-intelligence/frontend:dev ./frontend --build-arg NEXT_PUBLIC_API_URL=/api/v1

# 3. Push to STACKIT Container Registry
docker push registry.eu01.onstackit.cloud/research-intelligence/frontend:dev
```

### 4. Push the Applications
Trigger the Cloud Foundry push using the environment-specific manifest:

```bash
# Deploy to Development
cf push -f cf-manifests/manifest-dev.yml

# Deploy to Staging
cf push -f cf-manifests/manifest-stage.yml

# Deploy to Production
cf push -f cf-manifests/manifest-prod.yml
```

Upon executing this command, Cloud Foundry will:
1. Upload the `backend` code and compile it using the python buildpack.
2. Spin up containers for the Django API, Celery worker, and Celery beat.
3. Pull the Next.js/Nginx image from the container registry for the frontend dashboard.
4. Bind all containers to Postgres, Redis, and Object Storage.
5. Launch the containers and expose public HTTPS routes for the backend and frontend.

---

## 🔍 Step 3: Monitoring & Log Diagnostics

To inspect the status of your deployed instances (pods equivalent) and check error logs:

### List Deployed Containers:
```bash
# List all running apps and their instance counts in the current space
cf apps

# View status, CPU, memory, and state of individual instances of a specific app
cf app ri-dev-backend
```

### Check Logs:
```bash
# Stream real-time logs (stdout/stderr) from an app (equivalent to kubectl logs -f)
cf logs ri-dev-backend

# Dump the recent log buffer (equivalent to kubectl logs)
cf logs ri-dev-backend --recent
```
