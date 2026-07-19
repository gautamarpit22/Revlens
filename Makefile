.PHONY: setup data validate clean
setup:
	pip install -r requirements.txt --break-system-packages
data:
	cd data_simulator && python3 generate.py --out ../sample_data
validate:
	python3 ingestion/validate_contracts.py sample_data/events/events.ndjson contracts/product_event.v1.schema.json
clean:
	rm -rf sample_data
