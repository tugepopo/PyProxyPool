"""initial schema

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-03-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建所有初始表结构"""

    # proxies 表
    op.create_table(
        'proxies',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('ip', sa.String(45), nullable=False),
        sa.Column('port', sa.Integer, nullable=False),
        sa.Column('protocol', sa.String(10), default='http', nullable=False),
        sa.Column('username', sa.String(100), default='', nullable=False),
        sa.Column('password', sa.String(200), default='', nullable=False),
        sa.Column('anonymity', sa.String(20), default='unknown', nullable=False),
        sa.Column('country', sa.String(100), default='', nullable=False),
        sa.Column('area', sa.String(200), default='', nullable=False),
        sa.Column('speed', sa.Float, default=0.0),
        sa.Column('score', sa.Integer, default=10),
        sa.Column('last_verified', sa.Float, default=0.0),
        sa.Column('use_count', sa.Integer, default=0),
        sa.Column('source', sa.String(200), default='', nullable=False),
        sa.Column('outlet_ip', sa.String(45), default='', nullable=False),
        sa.Column('is_outbound_ip', sa.Boolean, default=False),
        # IP 纯净度
        sa.Column('purity_score', sa.Integer, default=0),
        sa.Column('purity_class', sa.String(50), default='', nullable=False),
        sa.Column('is_datacenter', sa.Boolean, default=False),
        sa.Column('is_proxy', sa.Boolean, default=False),
        sa.Column('is_vpn', sa.Boolean, default=False),
        sa.Column('is_tor', sa.Boolean, default=False),
        sa.Column('abuse_confidence', sa.Integer, default=0),
        sa.Column('isp', sa.String(200), default='', nullable=False),
        sa.Column('asn', sa.String(50), default='', nullable=False),
        sa.Column('asn_owner', sa.String(200), default='', nullable=False),
        sa.Column('org_name', sa.String(200), default='', nullable=False),
        sa.Column('ip_type', sa.String(50), default='', nullable=False),
        sa.Column('is_native', sa.Boolean, default=False),
        sa.Column('shared_users', sa.String(50), default='', nullable=False),
        sa.Column('risk_score', sa.Integer, default=0),
        sa.Column('risk_level', sa.String(20), default='', nullable=False),
        sa.Column('rdns', sa.String(200), default='', nullable=False),
        sa.Column('scenes', sa.Text, default='', nullable=False),
        sa.Column('ping0_location', sa.String(200), default='', nullable=False),
        sa.Column('ping0_latitude', sa.Float, default=0.0),
        sa.Column('ping0_longitude', sa.Float, default=0.0),
        # 四维度加权评分
        sa.Column('scan_score', sa.Float, default=0.0),
        sa.Column('grade', sa.String(1), default='', nullable=False),
        # 标签
        sa.Column('tags', sa.String(500), default='[]', nullable=False),
        # 时间戳
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # 唯一索引
    op.create_unique_constraint('uq_proxy_ip_port', 'proxies', ['ip', 'port'])
    op.create_index('idx_proxy_score', 'proxies', ['score'])
    op.create_index('idx_proxy_grade', 'proxies', ['grade'])
    op.create_index('idx_proxy_protocol', 'proxies', ['protocol'])
    op.create_index('idx_proxy_country', 'proxies', ['country'])
    op.create_index('idx_proxy_last_verified', 'proxies', ['last_verified'])
    op.create_index('idx_proxy_purity_class', 'proxies', ['purity_class'])

    # scan_tasks 表
    op.create_table(
        'scan_tasks',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('task_id', sa.String(64), unique=True, nullable=False),
        sa.Column('status', sa.String(20), default='pending', nullable=False),
        sa.Column('total', sa.Integer, default=0),
        sa.Column('processed', sa.Integer, default=0),
        sa.Column('valid', sa.Integer, default=0),
        sa.Column('invalid', sa.Integer, default=0),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # scan_results 表
    op.create_table(
        'scan_results',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('task_id', sa.String(64), sa.ForeignKey('scan_tasks.task_id'), nullable=False),
        sa.Column('ip', sa.String(45), nullable=False),
        sa.Column('port', sa.Integer, nullable=False),
        sa.Column('protocol', sa.String(10), default=''),
        sa.Column('is_valid', sa.Boolean, default=False),
        sa.Column('latency_ms', sa.Float, default=0.0),
        sa.Column('outlet_ip', sa.String(45), default=''),
        sa.Column('country', sa.String(100), default=''),
        sa.Column('isp', sa.String(200), default=''),
        sa.Column('asn', sa.String(50), default=''),
        sa.Column('error', sa.String(500), default=''),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index('idx_scan_result_task', 'scan_results', ['task_id'])

    # whitelist 表
    op.create_table(
        'whitelist',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('ip', sa.String(45), nullable=False),
        sa.Column('port', sa.Integer, nullable=False),
        sa.Column('protocol', sa.String(10), default='http'),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )
    op.create_unique_constraint('uq_whitelist_ip_port', 'whitelist', ['ip', 'port'])

    # blacklist 表
    op.create_table(
        'blacklist',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('ip', sa.String(45), nullable=False),
        sa.Column('port', sa.Integer, nullable=False),
        sa.Column('protocol', sa.String(10), default='http'),
        sa.Column('reason', sa.String(500), default=''),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )
    op.create_unique_constraint('uq_blacklist_ip_port', 'blacklist', ['ip', 'port'])


def downgrade() -> None:
    """回滚迁移"""
    op.drop_table('blacklist')
    op.drop_table('whitelist')
    op.drop_table('scan_results')
    op.drop_table('scan_tasks')
    op.drop_table('proxies')