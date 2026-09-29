"""Versioned status provenance, separate from payload deduplication.

Only explicit successful broker sections advance verified_at. Local duplicates,
empty inboxes, disabled providers and failed checks cannot attest freshness.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

PROVIDERS = {'Barclays', 'Hargreaves Lansdown', 'Trading 212'}
SECTIONS = {'holdings', 'orders', 'cash', 'transactions'}
REASONS = {'verified_changed', 'verified_unchanged', 'provider_failed', 'disabled',
           'needs_attention', 'not_verified', 'duplicate_payload', 'empty_inbox',
           'archive_failed', 'permission_denied', 'partial_coverage', 'timeout'}
ACTIONS = {'none', 'retry', 'configure', 'operator_review'}


def update_freshness(previous: dict[str, Any], step: dict[str, Any], attempted_at: str) -> dict[str, Any]:
    state = deepcopy(previous)
    name = step['name']
    if name not in PROVIDERS:
        return state
    prior = state.get(name, {})
    supplied = step.get('sections') or {}
    sections = set(prior) | set(supplied) | {'holdings', 'orders'}
    state[name] = {}
    for section in sections & SECTIONS:
        old = prior.get(section, {})
        new = supplied.get(section, {})
        status = new.get('status', step['status'])
        reason, action = {
            'failed': ('provider_failed', 'retry'),
            'needs_attention': ('needs_attention', 'operator_review'),
            'skipped': ('disabled', 'configure'),
            'disabled': ('disabled', 'configure'),
        }.get(status, ('not_verified', 'none'))
        observed = new.get('verified_at') if status in {'ok', 'imported', 'unchanged'} else None
        state[name][section] = {
            'last_attempt_at': attempted_at,
            'verified_at': observed or old.get('verified_at'),
            'valuation_at': new.get('valuation_at') if observed else old.get('valuation_at'),
            'coverage': new.get('coverage', 'unknown') if observed else old.get('coverage', 'unknown'),
            'status': status,
            'reason_code': new.get('reason_code') if new.get('reason_code') in REASONS else reason,
            'action_code': new.get('action_code') if new.get('action_code') in ACTIONS else action,
        }
    return state


def verified_sections(statuses: dict[str, str], observed_at: str, valuation_at: str | None) -> dict[str, Any]:
    sections = {}
    for section, status in statuses.items():
        verified = status in {'ok', 'imported', 'unchanged'}
        sections[section] = {
            'status': status if verified else 'needs_attention',
            'verified_at': observed_at if verified else None,
            'valuation_at': valuation_at if verified else None,
            'coverage': 'complete' if verified else 'partial',
            'reason_code': ('verified_changed' if status in {'ok', 'imported'} else 'verified_unchanged') if verified else 'partial_coverage',
            'action_code': 'none' if verified else 'operator_review',
        }
    return sections
