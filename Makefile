PYTHON ?= python3
.PHONY: demo test rtl rtl-tiny experiments clean
demo:
	$(PYTHON) -m tomasulo examples/hazards.asm --check --out build/hazards
test:
	$(PYTHON) -m unittest discover -s tests -v
rtl:
	$(PYTHON) scripts/verify_rtl.py
rtl-tiny:
	$(PYTHON) scripts/verify_rtl.py --profile tiny
experiments:
	$(PYTHON) scripts/experiments.py
clean:
	$(PYTHON) -c "import shutil; shutil.rmtree('build', ignore_errors=True)"
