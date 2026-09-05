# Repository, data, model, and license policy

This policy protects reproducibility without turning ordinary Git history into an unversioned research-data store.

## Belongs in Git

- source code and tests;
- database schemas and migrations;
- small synthetic or redistributable test fixtures;
- source and dataset manifests;
- checksums and artifact metadata;
- model and dataset cards;
- benchmark definitions and aggregated reports;
- documentation and experiment configuration.

Fixtures must be small, licensed for redistribution, and clearly marked as synthetic or sourced. They must not be extracted silently from restricted corpora.

## Stored outside ordinary Git history

- corpus dumps and full source snapshots;
- research `.db` stores and database journals;
- user uploads and museum images;
- generated exports;
- model checkpoints, tensor files, and optimizer state;
- embedding indexes and caches;
- intermediate training splits;
- private annotations or licensed source material.

External artifacts require a manifest containing:

- stable artifact identifier;
- content checksum;
- byte size and media type;
- creation or retrieval timestamp;
- source system and source version;
- license and redistribution status;
- producing code revision and parameters;
- storage locator that contains no secret credentials.

## Git LFS

The repository contains legacy LFS objects. Existing references remain intact while the foundation is developed. New datasets, model checkpoints, and optimizer state must not be added merely because LFS can store them.

Any history cleanup is a separate, reviewed migration because rewriting Git history affects every clone. Until then, `.gitattributes` retains only narrow rules needed by already tracked legacy objects and never tracks source code.

## Local paths

Runtime data paths come from `ISC_HELWIGII_*` environment variables. Developer-specific paths such as `~/Desktop/OxStealthData` are not valid package defaults.

## Generated evidence

Generated labels, translations, matches, embeddings, clusters, trees, and confidence scores are research artifacts. They require a manifest and method/model version. They do not become gold data until accepted through the governed review workflow.

## Secrets and personal data

API keys, tokens, credentials, environment files, private annotations, and user uploads must never be committed. Logs and exported experiment bundles must be checked for source licensing and personal information before sharing.

## Licensing boundary

Current repository files contain conflicting CC-BY-4.0 and MIT declarations. This policy does not relicense them.

Before a public release, the owner must approve explicit licenses for:

1. source code;
2. documentation;
3. original project data;
4. third-party corpus data;
5. generated annotations and benchmarks;
6. trained model weights.

No release should describe third-party corpus material, model weights, or generated data as covered by the source-code license unless that scope is documented and legally compatible.
