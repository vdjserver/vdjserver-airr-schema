include .env

PG_CONN=postgresql://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@$(POSTGRES_HOST)/postgres
PG_AK_CONN=postgresql://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@$(POSTGRES_HOST)/$(POSTGRES_DB)
PG_DISPLAY_CONN=postgresql://$(POSTGRES_USER):XXXXXX@$(POSTGRES_HOST)/$(POSTGRES_DB)
export IMPORT_DATA
export PG_AK_CONN
export POSTGRES_DB


help:
	@echo ""
	@echo "VDJServer AIRR Schema Pipeline"
	@echo "------------------------------------------------------------"
	@echo ""
	@echo "Using DB: $(PG_DISPLAY_CONN)"
	@echo "Host location of import folder: $(IMPORT_DATA)"
	@echo ""
	@echo "make docker             -- Build docker image"
	@echo ""
	@echo "Utility functions (outside docker)"
	@echo "make convert-airr-schema         -- convert airr schema to linkml"
	@echo "make convert-vdjserver-schema         -- convert vdjserver source schema to linkml"
	@echo "make comapre-schema         -- Comapre airr standards and vdjserver schema"
	@echo "generate-schema 		-- generate linkml schema"
	@echo ""
	@echo "------------------------------------------------------------"

# build docker image
docker:
	@echo "Building docker image"
	docker build . -t vdjserver/airr-schema:$(POSTGRES_DB)

convert-airr-schema:
	python3 src/vdjserver_airr_schema/scripts/airr2linkml.py \
		--airr_schema_yaml src/airr_schema/airr-standards-v2.0/specs/airr-schema.yaml \
		--output_file src/vdjserver_airr_schema/schema/airr_schema.yaml

convert-vdjserver-schema:
	python3 src/vdjserver_airr_schema/scripts/vdjserver2linkml.py \
		--source_schema src/vdjserver_airr_schema/scripts/vdjserver_schema_source.yaml \
		--output_file src/vdjserver_airr_schema/schema/vdjserver_schema.yaml


comapre-schema:
	python3 src/vdjserver_airr_schema/scripts/build_schema.py \
		-a src/airr_schema/airr-standards-v2.0/specs/airr-schema.yaml \
		-v src/vdjserver_airr_schema/scripts/vdjserver_schema_source.yaml

generate-schema:
	uv run linkml generate python src/vdjserver_airr_schema/schema/vdjserver_airr_schema.yaml 