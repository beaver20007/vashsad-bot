#!/bin/bash
echo "Seeding database..."
python scripts/seed_plants.py
python scripts/seed_promo.py
echo "All seeds applied!"
