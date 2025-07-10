#! /bin/bash

## Get current versions of requirements in sale.box image.
## Usage:
## sudo ./reqs_from_image.sh


set -e

image_tag='registry.saltbox.pro/saltbox/saltbox-core:master'

packages=()

while read -r line; do
  pkg=$(echo "$line" | grep --only-matching '^[a-zA-Z0-9-]*')
  [ -n "$pkg" ] && packages+=("$pkg")
done < requirements.txt

expr='$^'

for pkg in "${packages[@]}"; do
  expr="${expr}\|^${pkg}"
done

docker run --rm --entrypoint '/bin/bash' "$image_tag" -c 'pip3 freeze' | grep "$expr"
