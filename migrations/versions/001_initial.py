"""Initial migration — create all tables.

Revision ID: 001_initial
Revises: 
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enums
    op.execute("CREATE TYPE user_status AS ENUM ('ACTIVE', 'FLAGGED', 'RESTRICTED', 'BANNED')")
    op.execute("CREATE TYPE sponsor_status AS ENUM ('PENDING', 'APPROVED', 'SUSPENDED', 'BANNED')")
    op.execute("CREATE TYPE campaign_status AS ENUM ('DRAFT', 'PENDING', 'PENDING_FUNDING', 'ACTIVE', 'PAUSED', 'COMPLETED', 'EXPIRED', 'CANCELLED')")
    op.execute("CREATE TYPE task_type AS ENUM ('CHANNEL_JOIN', 'GROUP_JOIN', 'BOT_START', 'CHANNEL_GROUP_JOIN', 'FORCE_JOIN', 'CUSTOM')")
    op.execute("CREATE TYPE entity_type AS ENUM ('USER', 'SPONSOR', 'PLATFORM')")
    op.execute("CREATE TYPE transaction_type AS ENUM ('TASK_REWARD', 'REFERRAL_REWARD', 'REFERRAL_COMMISSION', 'WITHDRAWAL', 'WITHDRAWAL_RETURN', 'DEPOSIT', 'CAMPAIGN_FUND', 'CAMPAIGN_RELEASE', 'ADMIN_CREDIT', 'ADMIN_DEBIT')")
    op.execute("CREATE TYPE withdrawal_status AS ENUM ('PENDING', 'PROCESSING', 'PAID', 'FAILED', 'REJECTED')")
    op.execute("CREATE TYPE deposit_status AS ENUM ('PENDING', 'CONFIRMED', 'FAILED')")
    op.execute("CREATE TYPE flag_type AS ENUM ('DUPLICATE_ACCOUNT', 'RAPID_COMPLETION', 'SUSPICIOUS_REFERRAL', 'DUPLICATE_WALLET', 'EXCESSIVE_WITHDRAWAL', 'BOT_BEHAVIOR', 'ABNORMAL_GROWTH', 'REFERRAL_SELF_CHAIN', 'MULTIPLE_IPS', 'EARLY_WITHDRAWAL')")
    op.execute("CREATE TYPE flag_severity AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')")
    op.execute("CREATE TYPE ticket_category AS ENUM ('PAYMENT', 'TASK', 'WITHDRAWAL', 'REFERRAL', 'OTHER')")
    op.execute("CREATE TYPE ticket_status AS ENUM ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED')")

    # users
    op.create_table(
        'users',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('username', sa.String(64), nullable=True),
        sa.Column('first_name', sa.String(128), nullable=False),
        sa.Column('last_name', sa.String(128), nullable=True),
        sa.Column('status', postgresql.ENUM('ACTIVE', 'FLAGGED', 'RESTRICTED', 'BANNED', name='user_status', create_type=False), nullable=False, server_default='ACTIVE'),
        sa.Column('fraud_score', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('balance', sa.Numeric(18, 8), nullable=False, server_default='0'),
        sa.Column('total_earned', sa.Numeric(18, 8), nullable=False, server_default='0'),
        sa.Column('total_withdrawn', sa.Numeric(18, 8), nullable=False, server_default='0'),
        sa.Column('tasks_completed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tasks_skipped', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('bsc_wallet', sa.String(42), nullable=True),
        sa.Column('referrer_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('referral_code', sa.String(32), nullable=False, unique=True),
        sa.Column('is_sponsor', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('joined_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('last_active', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_users_referrer', 'users', ['referrer_id'])
    op.create_index('idx_users_status', 'users', ['status'])
    op.create_index('idx_users_referral_code', 'users', ['referral_code'])
    op.create_index('idx_users_bsc_wallet', 'users', ['bsc_wallet'])

    # sponsors
    op.create_table(
        'sponsors',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('company_name', sa.String(256), nullable=True),
        sa.Column('status', postgresql.ENUM('PENDING', 'APPROVED', 'SUSPENDED', 'BANNED', name='sponsor_status', create_type=False), nullable=False, server_default='PENDING'),
        sa.Column('available_balance', sa.Numeric(18, 8), nullable=False, server_default='0'),
        sa.Column('reserved_balance', sa.Numeric(18, 8), nullable=False, server_default='0'),
        sa.Column('total_deposited', sa.Numeric(18, 8), nullable=False, server_default='0'),
        sa.Column('total_spent', sa.Numeric(18, 8), nullable=False, server_default='0'),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approved_by', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('idx_sponsors_status', 'sponsors', ['status'])
    op.create_index('idx_sponsors_user_id', 'sponsors', ['user_id'])

    # campaigns
    op.create_table(
        'campaigns',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('sponsor_id', sa.Integer(), sa.ForeignKey('sponsors.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(256), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('task_type', postgresql.ENUM('CHANNEL_JOIN', 'GROUP_JOIN', 'BOT_START', 'CHANNEL_GROUP_JOIN', 'FORCE_JOIN', 'CUSTOM', name='task_type', create_type=False), nullable=False),
        sa.Column('telegram_chat_id', sa.BigInteger(), nullable=True),
        sa.Column('telegram_username', sa.String(64), nullable=True),
        sa.Column('invite_url', sa.Text(), nullable=True),
        sa.Column('reward_per_user', sa.Numeric(18, 8), nullable=False),
        sa.Column('completion_limit', sa.Integer(), nullable=False),
        sa.Column('completed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_budget', sa.Numeric(18, 8), nullable=False),
        sa.Column('reserved_budget', sa.Numeric(18, 8), nullable=False, server_default='0'),
        sa.Column('spent_budget', sa.Numeric(18, 8), nullable=False, server_default='0'),
        sa.Column('view_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('click_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_verify_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('skip_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', postgresql.ENUM('DRAFT', 'PENDING', 'PENDING_FUNDING', 'ACTIVE', 'PAUSED', 'COMPLETED', 'EXPIRED', 'CANCELLED', name='campaign_status', create_type=False), nullable=False, server_default='DRAFT'),
        sa.Column('approved_by', sa.BigInteger(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('idx_campaigns_status', 'campaigns', ['status'])
    op.create_index('idx_campaigns_sponsor', 'campaigns', ['sponsor_id'])
    op.create_index('idx_campaigns_expires', 'campaigns', ['expires_at'])

    # task_completions
    op.create_table(
        'task_completions',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('campaign_id', sa.Integer(), sa.ForeignKey('campaigns.id', ondelete='CASCADE'), nullable=False),
        sa.Column('reward_amount', sa.Numeric(18, 8), nullable=False),
        sa.Column('membership_status', sa.String(32), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('idempotency_key', sa.String(128), nullable=False, unique=True),
        sa.UniqueConstraint('user_id', 'campaign_id', name='uq_completion_user_campaign'),
    )
    op.create_index('idx_task_completions_user', 'task_completions', ['user_id'])
    op.create_index('idx_task_completions_campaign', 'task_completions', ['campaign_id'])

    # task_skips
    op.create_table(
        'task_skips',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('campaign_id', sa.Integer(), sa.ForeignKey('campaigns.id', ondelete='CASCADE'), nullable=False),
        sa.Column('skipped_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('user_id', 'campaign_id', name='uq_skip_user_campaign'),
    )
    op.create_index('idx_task_skips_user', 'task_skips', ['user_id'])

    # referrals
    op.create_table(
        'referrals',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('referrer_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('referred_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('reward_paid', sa.Numeric(18, 8), nullable=False, server_default='0'),
        sa.Column('commission_earned', sa.Numeric(18, 8), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('idx_referrals_referrer', 'referrals', ['referrer_id'])
    op.create_index('idx_referrals_referred', 'referrals', ['referred_id'])

    # transactions
    op.create_table(
        'transactions',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('entity_type', postgresql.ENUM('USER', 'SPONSOR', 'PLATFORM', name='entity_type', create_type=False), nullable=False),
        sa.Column('entity_id', sa.BigInteger(), nullable=False),
        sa.Column('tx_type', postgresql.ENUM('TASK_REWARD', 'REFERRAL_REWARD', 'REFERRAL_COMMISSION', 'WITHDRAWAL', 'WITHDRAWAL_RETURN', 'DEPOSIT', 'CAMPAIGN_FUND', 'CAMPAIGN_RELEASE', 'ADMIN_CREDIT', 'ADMIN_DEBIT', name='transaction_type', create_type=False), nullable=False),
        sa.Column('amount', sa.Numeric(18, 8), nullable=False),
        sa.Column('balance_before', sa.Numeric(18, 8), nullable=False),
        sa.Column('balance_after', sa.Numeric(18, 8), nullable=False),
        sa.Column('reference_type', sa.String(64), nullable=True),
        sa.Column('reference_id', sa.BigInteger(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('idempotency_key', sa.String(128), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('idx_transactions_entity', 'transactions', ['entity_type', 'entity_id'])
    op.create_index('idx_transactions_created', 'transactions', ['created_at'])
    op.create_index('idx_transactions_idempotency', 'transactions', ['idempotency_key'])

    # withdrawals
    op.create_table(
        'withdrawals',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('amount', sa.Numeric(18, 8), nullable=False),
        sa.Column('network', sa.String(16), nullable=False, server_default='BSC'),
        sa.Column('destination_wallet', sa.String(42), nullable=False),
        sa.Column('status', postgresql.ENUM('PENDING', 'PROCESSING', 'PAID', 'FAILED', 'REJECTED', name='withdrawal_status', create_type=False), nullable=False, server_default='PENDING'),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('tx_hash', sa.String(66), nullable=True),
        sa.Column('block_number', sa.BigInteger(), nullable=True),
        sa.Column('gas_used', sa.BigInteger(), nullable=True),
        sa.Column('retry_count', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('idempotency_key', sa.String(128), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_withdrawals_status', 'withdrawals', ['status'])
    op.create_index('idx_withdrawals_user', 'withdrawals', ['user_id'])
    op.create_index('idx_withdrawals_created', 'withdrawals', ['created_at'])

    # deposits
    op.create_table(
        'deposits',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('sponsor_id', sa.Integer(), sa.ForeignKey('sponsors.id', ondelete='CASCADE'), nullable=False),
        sa.Column('amount', sa.Numeric(18, 8), nullable=False),
        sa.Column('network', sa.String(16), nullable=False, server_default='BSC'),
        sa.Column('tx_hash', sa.String(66), nullable=False, unique=True),
        sa.Column('from_address', sa.String(42), nullable=True),
        sa.Column('block_number', sa.BigInteger(), nullable=True),
        sa.Column('confirmations', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', postgresql.ENUM('PENDING', 'CONFIRMED', 'FAILED', name='deposit_status', create_type=False), nullable=False, server_default='PENDING'),
        sa.Column('credited_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('idx_deposits_sponsor', 'deposits', ['sponsor_id'])
    op.create_index('idx_deposits_status', 'deposits', ['status'])
    op.create_index('idx_deposits_tx_hash', 'deposits', ['tx_hash'])

    # fraud_flags
    op.create_table(
        'fraud_flags',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('flag_type', postgresql.ENUM('DUPLICATE_ACCOUNT', 'RAPID_COMPLETION', 'SUSPICIOUS_REFERRAL', 'DUPLICATE_WALLET', 'EXCESSIVE_WITHDRAWAL', 'BOT_BEHAVIOR', 'ABNORMAL_GROWTH', 'REFERRAL_SELF_CHAIN', 'MULTIPLE_IPS', 'EARLY_WITHDRAWAL', name='flag_type', create_type=False), nullable=False),
        sa.Column('severity', postgresql.ENUM('LOW', 'MEDIUM', 'HIGH', 'CRITICAL', name='flag_severity', create_type=False), nullable=False),
        sa.Column('details', postgresql.JSONB(), nullable=True),
        sa.Column('reviewed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('reviewed_by', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('idx_fraud_flags_user', 'fraud_flags', ['user_id'])
    op.create_index('idx_fraud_flags_reviewed', 'fraud_flags', ['reviewed'])
    op.create_index('idx_fraud_flags_severity', 'fraud_flags', ['severity'])

    # force_join_channels
    op.create_table(
        'force_join_channels',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('chat_id', sa.BigInteger(), nullable=False, unique=True),
        sa.Column('username', sa.String(64), nullable=True),
        sa.Column('invite_url', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )

    # support_tickets
    op.create_table(
        'support_tickets',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('ticket_code', sa.String(16), nullable=False, unique=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('category', postgresql.ENUM('PAYMENT', 'TASK', 'WITHDRAWAL', 'REFERRAL', 'OTHER', name='ticket_category', create_type=False), nullable=False),
        sa.Column('subject', sa.String(256), nullable=False),
        sa.Column('message', sa.String(2000), nullable=True),
        sa.Column('status', postgresql.ENUM('OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED', name='ticket_status', create_type=False), nullable=False, server_default='OPEN'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_support_tickets_user', 'support_tickets', ['user_id'])
    op.create_index('idx_support_tickets_status', 'support_tickets', ['status'])

    # audit_logs
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('admin_id', sa.BigInteger(), nullable=False),
        sa.Column('action', sa.String(64), nullable=False),
        sa.Column('target_type', sa.String(32), nullable=True),
        sa.Column('target_id', sa.BigInteger(), nullable=True),
        sa.Column('old_value', postgresql.JSONB(), nullable=True),
        sa.Column('new_value', postgresql.JSONB(), nullable=True),
        sa.Column('ip_address', postgresql.INET(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('idx_audit_logs_admin', 'audit_logs', ['admin_id'])
    op.create_index('idx_audit_logs_target', 'audit_logs', ['target_type', 'target_id'])
    op.create_index('idx_audit_logs_created', 'audit_logs', ['created_at'])

    # platform_settings
    op.create_table(
        'platform_settings',
        sa.Column('key', sa.String(128), primary_key=True),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('updated_by', sa.BigInteger(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )

    # wallets
    op.create_table(
        'wallets',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('address', sa.String(42), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('idx_wallets_user', 'wallets', ['user_id'])
    op.create_index('idx_wallets_address', 'wallets', ['address'])

    # Seed default platform settings
    op.execute("""
        INSERT INTO platform_settings (key, value, description) VALUES
        ('referral_reward', '0.010', 'Fixed USDT reward per new referral'),
        ('referral_commission_pct', '10', 'Percentage of task reward paid to referrer'),
        ('min_withdrawal', '0.12', 'Minimum withdrawal amount in USDT'),
        ('max_withdrawal', '100.00', 'Maximum withdrawal amount in USDT'),
        ('task_min_reward', '0.001', 'Minimum allowed reward per task'),
        ('task_max_reward', '1.000', 'Maximum allowed reward per task'),
        ('sponsor_min_deposit', '1.00', 'Minimum sponsor deposit in USDT'),
        ('withdrawal_network', 'BSC', 'Payout network'),
        ('force_join_enabled', 'true', 'Enforce channel membership gate'),
        ('maintenance_mode', 'false', 'Enable maintenance mode'),
        ('auto_payout_enabled', 'true', 'Enable automatic payout processing'),
        ('min_deposit_confirmations', '12', 'BSC confirmations before crediting deposit'),
        ('fraud_auto_ban_score', '76', 'Fraud score threshold for auto-ban')
    """)


def downgrade() -> None:
    op.drop_table('wallets')
    op.drop_table('platform_settings')
    op.drop_table('audit_logs')
    op.drop_table('support_tickets')
    op.drop_table('force_join_channels')
    op.drop_table('fraud_flags')
    op.drop_table('deposits')
    op.drop_table('withdrawals')
    op.drop_table('transactions')
    op.drop_table('referrals')
    op.drop_table('task_skips')
    op.drop_table('task_completions')
    op.drop_table('campaigns')
    op.drop_table('sponsors')
    op.drop_table('users')

    for enum_name in [
        'user_status', 'sponsor_status', 'campaign_status', 'task_type',
        'entity_type', 'transaction_type', 'withdrawal_status', 'deposit_status',
        'flag_type', 'flag_severity', 'ticket_category', 'ticket_status',
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
