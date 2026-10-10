.DEFAULT_GOAL := reproduce

.PHONY: help reproduce bootstrap generate build assemble certs up down verify test artifacts size lint status

reproduce: ## Fetch, build, test BLS/inference and collect all artifacts.
	./triton

help:
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "%-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

bootstrap: ## Build tooling and fetch the exact pinned Triton source.
	./scripts/bootstrap.sh

generate: bootstrap ## Generate (but do not execute) NVIDIA's build stages.
	./scripts/generate.sh

build: ## Fetch dependencies and build the default CPU-only image.
	./triton build

assemble: ## Repackage cached artifacts; pass options through ASSEMBLE_ARGS.
	./scripts/assemble.sh $(ASSEMBLE_ARGS)

certs: ## Generate a local development CA and TLS certificate.
	./scripts/generate-dev-certs.sh

up: ## Start Triton behind the HTTPS/gRPCS gateway.
	./triton run

down: ## Stop the local stack without deleting images or models.
	./triton stop

verify: ## Verify backends, TLS endpoints, shared memory, and observability.
	./scripts/verify.sh

test: ## Test backend inference, Python BLS, custom metrics and shared memory.
	./triton test

artifacts: ## Collect generated Dockerfiles, provenance, SBOM, and optional archive.
	./triton artifacts

size: ## Measure runtime bytes by dependency inside Docker.
	./scripts/image-size.sh

lint: ## Run shell and Compose static validation in Docker.
	./scripts/lint.sh

status: ## Show service and local image status.
	docker compose ps
	docker image inspect local/tritonserver-cpu:26.09 --format '{{.Id}} {{.Size}} bytes' 2>/dev/null || true

