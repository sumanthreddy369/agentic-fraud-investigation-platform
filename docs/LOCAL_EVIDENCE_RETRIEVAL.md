# Local evidence retrieval

`LocalEvidenceRetriever` implements the read-only `get_case_evidence` tool contract
for the checkpointed investigation workflow. A trusted caller supplies the evidence
collection and authenticated case scope. It does not discover files, query a shared
database or contact an external provider.

Filtering requires matching case ID, owner and model domain before any ranking.
Ranking counts distinct case-insensitive query tokens appearing in each excerpt;
evidence ID breaks ties deterministically. Unmatched queries return no evidence.
Scores are lexical overlap counts, not fraud probabilities or confidence estimates.

The collection is limited to 1,000 records, excerpts to 4,000 characters, identifiers
to 128 characters and results to at most 20 records. Duplicate identifiers inside
the same scope are rejected. Collection construction consumes bounded input even
when the caller supplies a generator.

Returned records retain their classification and disclosure approval. Retrieval
does not approve external transmission, establish that evidence is true, or make
an enforcement decision. The workflow's default output still requires human review.

Tests cover each scope dimension, unauthorized actors, deterministic ranking,
empty matches, collection limits, disclosure controls and workflow integration.
This is a local lexical baseline. Persistent search, semantic retrieval, MCP and
live provider integration remain **Target (not built yet)** for this component.
