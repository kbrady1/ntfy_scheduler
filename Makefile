INSTALL_DIR := /usr/local/bin
BINARY := ntfyScheduler
SCRIPT := $(shell pwd)/ntfy.py

.PHONY: install uninstall

install:
	chmod +x $(SCRIPT)
	ln -sf $(SCRIPT) $(INSTALL_DIR)/$(BINARY)
	@echo "Installed: $(INSTALL_DIR)/$(BINARY)"

uninstall:
	rm -f $(INSTALL_DIR)/$(BINARY)
	@echo "Uninstalled: $(INSTALL_DIR)/$(BINARY)"
