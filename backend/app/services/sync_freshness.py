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
            'coverage_start': new.get('coverage_start') if observed else old.get('coverage_start'),
            'coverage_end': new.get('coverage_end') if observed else old.get('coverage_end'),
            'status': status,
            'reason_code': new.get('reason_code') if new.get('reason_code') in REASONS else reason,
            'action_code': new.get('action_code') if new.get('action_code') in ACTIONS else action,
        }
    return state


REQUIRED_SECTIONS = {
    'Trading 212': {'holdings', 'orders', 'cash', 'transactions'},
    'Barclays': {'holdings', 'orders'},
    'Hargreaves Lansdown': {'holdings', 'orders'},
}


def verified_sections(statuses: dict[str, str], observed_at: str, valuation_at: str | None,
                      *, coverage: dict[str, str] | None = None,
                      ranges: dict[str, tuple[str, str]] | None = None) -> dict[str, Any]:
    sections = {}
    for section, status in statuses.items():
        verified = status in {'ok', 'imported', 'unchanged'}
        sections[section] = {
            'status': status if verified else 'needs_attention',
            'verified_at': observed_at if verified else None,
            'valuation_at': valuation_at if verified and section in {'holdings', 'cash'} else None,
            'coverage': (coverage or {}).get(section, 'unknown') if verified else 'partial',
            'reason_code': ('verified_changed' if status in {'ok', 'imported'} else 'verified_unchanged') if verified else 'partial_coverage',
            'action_code': 'none' if verified else 'operator_review',
        }
        if sections[section]['coverage'] != 'complete':
            sections[section]['reason_code'] = 'partial_coverage'
            sections[section]['action_code'] = 'operator_review'
        if ranges and section in ranges:
            sections[section]['coverage_start'], sections[section]['coverage_end'] = ranges[section]
    return sections
