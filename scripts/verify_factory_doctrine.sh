#!/usr/bin/env sh
# verify_factory_doctrine.sh
# Verifies that blockstor-derived Factory doctrine files are discoverable.
set -eu

echo "Verifying Factory blockstor-derived doctrine..."

test -f docs/doctrine/blockstor-derived-rules.md || { echo "FAIL: blockstor-derived-rules.md not found"; exit 1; }
grep -q "Blockstor-Derived Factory Rules" docs/doctrine/blockstor-derived-rules.md || { echo "FAIL: title not found"; exit 1; }
grep -q "clean-room" docs/doctrine/blockstor-derived-rules.md || { echo "FAIL: clean-room section not found"; exit 1; }
grep -q "Cold Resume" docs/doctrine/blockstor-derived-rules.md || { echo "FAIL: cold-resume section not found"; exit 1; }
grep -q "Release Certification" docs/doctrine/blockstor-derived-rules.md || { echo "FAIL: release-certification section not found"; exit 1; }

test -f docs/templates/release-certification.md || { echo "FAIL: release-certification template not found"; exit 1; }
test -f docs/templates/cold-resume.md || { echo "FAIL: cold-resume template not found"; exit 1; }

grep -q "blockstor-derived-rules.md" docs/doctrine/seed_rules.md || { echo "FAIL: seed_rules link not found"; exit 1; }
grep -q "Blockstor-derived review checks" docs/doctrine/playbooks/design_review.md || { echo "FAIL: design_review checklist not found"; exit 1; }

echo "PASS: Factory blockstor-derived doctrine is discoverable"
