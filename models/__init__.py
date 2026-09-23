"""
Models package — import all models to register with SQLAlchemy metadata.
"""
from models.user import User, UserStatus
from models.sponsor import Sponsor, SponsorStatus
from models.campaign import Campaign, CampaignStatus, TaskType
from models.task_completion import TaskCompletion
from models.task_skip import TaskSkip
from models.referral import Referral
from models.transaction import Transaction, TransactionType, EntityType
from models.withdrawal import Withdrawal, WithdrawalStatus
from models.deposit import Deposit, DepositStatus
from models.fraud_flag import FraudFlag, FlagType, FlagSeverity
from models.force_join import ForceJoinChannel
from models.support_ticket import SupportTicket, TicketCategory, TicketStatus
from models.audit_log import AuditLog
from models.settings import PlatformSetting
from models.wallet import Wallet

__all__ = [
    "User", "UserStatus",
    "Sponsor", "SponsorStatus",
    "Campaign", "CampaignStatus", "TaskType",
    "TaskCompletion",
    "TaskSkip",
    "Referral",
    "Transaction", "TransactionType", "EntityType",
    "Withdrawal", "WithdrawalStatus",
    "Deposit", "DepositStatus",
    "FraudFlag", "FlagType", "FlagSeverity",
    "ForceJoinChannel",
    "SupportTicket", "TicketCategory", "TicketStatus",
    "AuditLog",
    "PlatformSetting",
    "Wallet",
]
