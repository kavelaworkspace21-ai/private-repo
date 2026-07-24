"""billing: subscription_plans, subscriptions, usage_events, invoices, webhook_events

LSAI-V3-05 · Gate G11 · Phase C. Adds ONLY the five billing tables. The autogenerate
also detected pre-existing index/NOT-NULL drift on unrelated tables (clients, cases,
diary_*, users, …) — that belongs to a separate schema-hygiene migration, not this
billing sprint, so it is deliberately excluded here to keep the change reviewable.

Revision ID: 3a7a23076413
Revises: d7e3b1a9c4f2
Create Date: 2026-07-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3a7a23076413'
down_revision: Union[str, Sequence[str], None] = 'd7e3b1a9c4f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'subscription_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=40), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('price_monthly_inr', sa.Integer(), nullable=True),
        sa.Column('price_annual_inr', sa.Integer(), nullable=True),
        sa.Column('billing', sa.String(length=20), nullable=False),
        sa.Column('per_seat', sa.Boolean(), nullable=False),
        sa.Column('min_seats', sa.Integer(), nullable=True),
        sa.Column('trial_days', sa.Integer(), nullable=False),
        sa.Column('limits', sa.JSON(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_subscription_plans_code'), 'subscription_plans', ['code'], unique=True)
    op.create_index(op.f('ix_subscription_plans_id'), 'subscription_plans', ['id'], unique=False)

    op.create_table(
        'subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('plan_code', sa.String(length=40), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('billing_cycle', sa.String(length=10), nullable=False),
        sa.Column('seats', sa.Integer(), nullable=False),
        sa.Column('current_period_start', sa.DateTime(), nullable=False),
        sa.Column('current_period_end', sa.DateTime(), nullable=False),
        sa.Column('trial_end', sa.DateTime(), nullable=True),
        sa.Column('razorpay_subscription_id', sa.String(length=80), nullable=True),
        sa.Column('razorpay_customer_id', sa.String(length=80), nullable=True),
        sa.Column('founding_member', sa.Boolean(), nullable=False),
        sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False),
        sa.Column('canceled_at', sa.DateTime(), nullable=True),
        sa.Column('gstin', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_subscriptions_id'), 'subscriptions', ['id'], unique=False)
    op.create_index(op.f('ix_subscriptions_razorpay_subscription_id'), 'subscriptions', ['razorpay_subscription_id'], unique=False)
    op.create_index(op.f('ix_subscriptions_tenant_id'), 'subscriptions', ['tenant_id'], unique=True)

    op.create_table(
        'usage_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_usage_events_created_at'), 'usage_events', ['created_at'], unique=False)
    op.create_index(op.f('ix_usage_events_id'), 'usage_events', ['id'], unique=False)
    op.create_index(op.f('ix_usage_events_kind'), 'usage_events', ['kind'], unique=False)
    op.create_index(op.f('ix_usage_events_tenant_id'), 'usage_events', ['tenant_id'], unique=False)

    op.create_table(
        'invoices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('subscription_id', sa.Integer(), nullable=False),
        sa.Column('amount_paise', sa.Integer(), nullable=False),
        sa.Column('gst_paise', sa.Integer(), nullable=False),
        sa.Column('total_paise', sa.Integer(), nullable=False),
        sa.Column('gst_rate_percent', sa.Integer(), nullable=False),
        sa.Column('gstin', sa.String(length=20), nullable=True),
        sa.Column('invoice_number', sa.String(length=40), nullable=False),
        sa.Column('period_start', sa.DateTime(), nullable=False),
        sa.Column('period_end', sa.DateTime(), nullable=False),
        sa.Column('razorpay_payment_id', sa.String(length=80), nullable=True),
        sa.Column('pdf_path', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_invoices_id'), 'invoices', ['id'], unique=False)
    op.create_index(op.f('ix_invoices_invoice_number'), 'invoices', ['invoice_number'], unique=True)
    op.create_index(op.f('ix_invoices_razorpay_payment_id'), 'invoices', ['razorpay_payment_id'], unique=False)
    op.create_index(op.f('ix_invoices_subscription_id'), 'invoices', ['subscription_id'], unique=False)
    op.create_index(op.f('ix_invoices_tenant_id'), 'invoices', ['tenant_id'], unique=False)

    op.create_table(
        'webhook_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.String(length=120), nullable=False),
        sa.Column('event_type', sa.String(length=60), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_webhook_events_event_id'), 'webhook_events', ['event_id'], unique=True)
    op.create_index(op.f('ix_webhook_events_id'), 'webhook_events', ['id'], unique=False)
    op.create_index(op.f('ix_webhook_events_tenant_id'), 'webhook_events', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_table('webhook_events')
    op.drop_table('invoices')
    op.drop_table('usage_events')
    op.drop_table('subscriptions')
    op.drop_table('subscription_plans')
