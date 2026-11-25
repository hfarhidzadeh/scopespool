# Public name review

## Current name, 2026-11-24

The GitHub repository was renamed to [ScopeSpool](https://github.com/hfarhidzadeh/scopespool).
The applied rename covers the repository name. The installed package and
command currently use `memvane`, and Python imports use `dynmemory`.

## ScopeSpool exact-name check, 2026-11-25

An [exact-name GitHub repository search](https://api.github.com/search/repositories?q=scopespool%20in%3Aname&per_page=100)
returned only [this repository](https://github.com/hfarhidzadeh/scopespool).
Exact package lookups returned no entry on [PyPI](https://pypi.org/pypi/scopespool/json),
[npm](https://registry.npmjs.org/scopespool), or
[crates.io](https://crates.io/api/v1/crates/scopespool). Broad quoted web
searches found no independent exact-name software project. This is a
time-limited public software check.

RDAP lookups returned no registry record for `scopespool.com`, `.net`, `.org`,
`.dev`, `.ai`, `.io`, or `.app` at the time of checking; for example, see the
[`.com` lookup](https://rdap.verisign.com/com/v1/domain/scopespool.com).
An absent RDAP record is not a guarantee that a domain can be registered.
Formal trademark clearance remains open; use the
[USPTO trademark search](https://tmsearch.uspto.gov/search/) before a public
launch.

## Memvane collision check, 2026-11-24

**Recommendation: choose a different public name.** A second public project
uses **MemVane** for a plugin that retrieves project documents, notes, and
wiki context for coding agents. Its name matched the former repository name when case is ignored, and both
projects serve agent memory or context workflows.
[Other MemVane project](https://github.com/zbdulee/memvane)

Verisign records `memvane.com` as registered since September 13, 2026.
Registrant identity and any relationship to the other project are
unconfirmed. The exact PyPI and npm registry lookups returned 404 at the time
of this check. Registry occupancy can change separately from public name use.
[Verisign registration record](https://rdap.verisign.com/com/v1/domain/memvane.com)
· [PyPI lookup](https://pypi.org/pypi/memvane/json)
· [npm registry lookup](https://registry.npmjs.org/memvane)

This check documents a software naming collision. Formal trademark clearance
remains outside its scope. Use the [USPTO search](https://tmsearch.uspto.gov/search/),
[WIPO Global Brand Database](https://www.wipo.int/en/web/global-brand-database/index),
and [EUIPO search tools](https://www.euipo.europa.eu/en/search-ip) for a formal launch review.

## Original decision, 2026-11-19

**Decision: rename this project to Memvane (repository/package/CLI: `memvane`).**
The owner selected this name on 2026-11-19. Initial exact-name web searches,
including GitHub, arXiv, and PyPI queries, found no obvious published memory
system or software package named Memvane; this is a preliminary collision check.

The former name “Memora” has an
exact-name collision with published work in agent memory, including work
evaluated on LongMemEval.

Primary sources checked:

| Published use | Evidence | Relevance |
| --- | --- | --- |
| *Memora: A Harmonic Memory Representation Balancing Abstraction and Specificity*, Xia et al. | [arXiv:2602.03315](https://arxiv.org/abs/2602.03315), first submitted February 3, 2026; [official Microsoft repository](https://github.com/microsoft/Memora) | An agent-memory system, with memory updates and retrieval; a direct collision in this project's field. |
| Memora benchmark, introduced in *From Recall to Forgetting: Benchmarking Long-Term Memory for Personalized Agents*, Uddin et al. | [ACL Findings 2026 publication](https://aclanthology.org/2026.findings-acl.1337/), July 2026; [authors' repository](https://github.com/geniesinc/Memora) | A second exact-name use in long-term memory evaluation. |

This establishes a research/software naming collision. A different package
suffix, such as the former `memora-agent-memory`, would still leave the paper
title, README, and `memora` command ambiguous.

The rename updates the README/title, package metadata, CLI name/help/examples,
and current experiment code. Existing result reports retain Memora as the name
used for those historical runs; published systems cited above also retain their
names. The Python module remains `dynmemory`, and the default database filename
remains `.memora.sqlite3` so an upgrade continues to open the existing store.
