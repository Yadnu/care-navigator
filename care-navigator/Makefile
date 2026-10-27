PYTHON ?= python

.PHONY: data guide test eval demo app

data: guide
	$(PYTHON) data/generate.py

guide:
	$(PYTHON) data/build_symptom_guide.py

test:
	$(PYTHON) -m pytest

eval:
	$(PYTHON) scripts/run_eval.py

demo:
	$(PYTHON) cli.py

app:
	$(PYTHON) -m streamlit run app.py
