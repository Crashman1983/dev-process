# ADR-0001: Record architecture decisions

## Status

Accepted

## Type

process

## Intent

keep

## Context

Architectural choices outlive the conversations that produced them. Without a
durable record, the *why* behind a structure is lost, and later work either
cargo-cults or accidentally reverses it. The development process needs one
place where decisions, their status, and their endorsement live.

## Decision

We will record significant, hard-to-reverse decisions — architectural, product,
or process — as decision records in `docs/process/adr/`, one decision per file,
named `adr-NNNN-<slug>.md`, using the axes of `template.md`: `Status`
(lifecycle), `Type` (which kind of decision), and `Intent` (endorsement). Every
new record is added to the index in `README.md`.

## Consequences

Decisions become reviewable, referenceable (stories and architecture rules
link `ADR-NNNN`), and honestly labeled — "so it is" stays separate from "so it
shall become". The cost is the discipline of writing them; the tier routing
keeps that cost on the changes where it pays.
