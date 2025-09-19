#!/bin/bash
cd /home/kavia/workspace/code-generation/food-order-tracker-22822-22831/food_order_backend
source venv/bin/activate
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

