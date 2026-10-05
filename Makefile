.PHONY: setup proto db server web run clean

VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

setup:                ## create venv + install deps + generate stubs
	python3 -m venv $(VENV)
	$(PIP) install -q -r requirements.txt
	$(MAKE) proto
	$(PY) database.py

proto:                ## regenerate gRPC stubs from protos/shipping.proto
	$(PY) -m grpc_tools.protoc -I protos \
		--python_out=. --grpc_python_out=. protos/shipping.proto

db:                   ## (re)initialize the SQLite database
	$(PY) database.py

server:               ## run the vulnerable gRPC backend (:50051)
	$(PY) server.py

web:                  ## run the Flask web front end (:8000)
	$(PY) web.py

run:                  ## run backend + web together
	$(PY) server.py & sleep 2 && $(PY) web.py

clean:
	rm -rf $(VENV) nusakirim.db shipping_pb2.py shipping_pb2_grpc.py __pycache__
