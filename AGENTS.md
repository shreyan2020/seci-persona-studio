# Interface workspace

This repository owns the SECI Persona Studio application and portable public example.
The sibling `dsm-interface` workspace owns ongoing research experiments and their chats.
Do not modify that research workspace as part of routine interface changes.

Keep runtime databases, interviews, full PDFs, and local model responses out of commits.
The bundled example is a curated, source-reviewed snapshot; preserve its provenance.
Verify frontend changes with TypeScript and a production build. Use relevant backend
unit tests for evidence, role orchestration, and reversible decision-rule changes.
Historical evaluation reports in docs are snapshots, not newly run experiments.
