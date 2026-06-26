.PHONY: repackage doctor

# Regenerate plugins/workflow-shell/ from canonical .claude/ and stamp provenance.
# Override knobs: CANONICAL_REPO=… INCLUDE_STACK_RULES=… PROMOTE_PROTECT_SECRETS=… PLUGIN_VERSION=…
repackage:
	@bash scripts/repackage.sh

# Is the packaged plugin behind canonical on the packaged surface?
doctor:
	@bash scripts/check-drift.sh
