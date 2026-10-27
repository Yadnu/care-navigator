PYTHON ?= python

.PHONY: data test eval demo app

data:
	$(PYTHON) data/generate.py

test:
	$(PYTHON) -m pytest

eval:
	$(PYTHON) scripts/run_eval.py

demo:
	$(PYTHON) cli.py

app:
	$(PYTHON) -m streamlit run app.py
