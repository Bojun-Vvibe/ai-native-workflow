# Project Plan (final)

## Overview

This document describes the rollout plan for the new ingestion pipeline.

## Milestones

- M1: schema freeze, confirmed with data team
- M2: backfill, numbers locked
- M3: cutover

## Owner

Owner: Bojun

## Risks

- Latency: bounded by p99 of upstream
- Cost: within quarterly envelope

## Detailed steps

1. Drain queue.
2. Snapshot.
3. Replay diffs.
4. Switch traffic.

## Notes

The legacy router is replaced at M3.
