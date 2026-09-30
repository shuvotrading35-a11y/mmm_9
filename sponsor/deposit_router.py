"""Sponsor deposit router — 3 methods: Binance Pay, X Rocket, BEP20."""
from decimal import Decimal, InvalidOperation

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import settings
from database import get_session

log = structlog.get_logger(__name__)


async def show_deposit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the 3-method deposit menu — like the screenshot."""
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💠 Binance Pay", callback_data="dep_amt:binance"),
            InlineKeyboardButton("✅ X Rocket", callback_data="dep_amt:xrocket"),
        ],
        [
            InlineKeyboardButton("🌐 USDT (BEP20)", callback_data="dep_amt:bep20"),
        ],
        [InlineKeyboardButton("🔙 Back to Sponsor Panel", callback_data="sponsor:back")],
    ])

    text = (
        "💰 <b>DEPOSIT HUB</b>\n\n"
        "Please select your preferred network or gateway to deposit funds.\n\n"
        "• 💠 <b>Binance Pay</b> — send to Binance Pay ID + screenshot\n"
        "• ✅ <b>X Rocket</b> — instant checkout (auto-credit)\n"
        "• 🌐 <b>USDT (BEP20)</b> — on-chain transfer + tx hash\n"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=kb
        )
    else:
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=kb
        )


async def prompt_deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User tapped a method → ask for amount."""
    query = update.callback_query
    await query.answer()

    method = query.data.split(":")[1]
    context.user_data["deposit_method"] = method
    context.user_data["awaiting_deposit_amount"] = True

    if method == "binance":
        title = "💠 <b>BINANCE PAY DEPOSIT DASHBOARD</b>"
        min_amt, max_amt = settings.BINANCE_PAY_MIN, settings.BINANCE_PAY_MAX
    elif method == "bep20":
        title = "🌐 <b>USDT (BEP20) DEPOSIT DASHBOARD</b>"
        min_amt, max_amt = settings.BEP20_MIN, settings.BEP20_MAX
    else:
        title = "✅ <b>X ROCKET DEPOSIT DASHBOARD</b>"
        min_amt, max_amt = settings.SPONSOR_MIN_DEPOSIT, Decimal("500")

    text = (
        f"{title}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📥 Minimum: <b>{min_amt} USDT</b>\n"
        f"📤 Maximum: <b>{max_amt} USDT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💬 How much USDT do you want to deposit?\n"
        f"Please type the amount here:"
    )

    await query.edit_message_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="sponsor:cancel")]
        ]),
    )


async def handle_deposit_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Called when sponsor types amount."""
    text = (update.message.text or "").strip()
    method = context.user_data.get("deposit_method") or "xrocket"

    try:
        amount = Decimal(text)
        if amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await update.message.reply_text("❌ Invalid amount. Type a number.")
        return

    if method == "binance":
        min_amt, max_amt = settings.BINANCE_PAY_MIN, settings.BINANCE_PAY_MAX
    elif method == "bep20":
        min_amt, max_amt = settings.BEP20_MIN, settings.BEP20_MAX
    else:
        min_amt, max_amt = settings.SPONSOR_MIN_DEPOSIT, Decimal("500")

    if amount < min_amt:
        await update.message.reply_text(f"❌ Minimum: {min_amt} USDT")
        return
    if amount > max_amt:
        await update.message.reply_text(f"❌ Maximum: {max_amt} USDT")
        return

    context.user_data["awaiting_deposit_amount"] = False

    async with get_session() as session:
        from services.sponsor_service import SponsorService
        sponsor = await SponsorService.get_sponsor_by_user(
            session, update.effective_user.id
        )
        if not sponsor:
            await update.message.reply_text("❌ Sponsor account not found.")
            return

        if method == "binance":
            await _dispatch_binance(update, context, session, sponsor, amount)
        elif method == "bep20":
            await _dispatch_bep20(update, context, session, sponsor, amount)
        else:
            await _dispatch_xrocket(update, context, session, sponsor, amount)


async def _dispatch_binance(update, context, session, sponsor, amount):
    from services.manual_deposit_service import ManualDepositService
    try:
        result = await ManualDepositService.create_binance_pay_deposit(
            session, sponsor.id, amount
        )
        await session.commit()
    except Exception as e:
        log.exception("Binance deposit create failed")
        await update.message.reply_text(f"❌ Failed: {str(e)[:200]}")
        return

    text = (
        f"📥 <b>BINANCE PAY PAYMENT DETAILS</b> 💠\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 Amount: <b>{amount} USDT</b>\n"
        f"🆔 Binance Pay ID: <code>{result['binance_pay_id']}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💬 Send the amount to the Binance Pay ID above,\n"
        f"then send a <b>screenshot of your payment</b> here:"
    )
    await update.message.reply_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="sponsor:cancel")]
        ]),
    )
    context.user_data["awaiting_deposit_screenshot"] = result["deposit_id"]


async def _dispatch_bep20(update, context, session, sponsor, amount):
    from services.manual_deposit_service import ManualDepositService
    try:
        result = await ManualDepositService.create_bep20_deposit(
            session, sponsor.id, amount
        )
        await session.commit()
    except Exception as e:
        log.exception("BEP20 deposit create failed")
        await update.message.reply_text(f"❌ Failed: {str(e)[:200]}")
        return

    text = (
        f"🌐 <b>USDT (BEP20) DEPOSIT</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 Amount: <b>{amount} USDT</b>\n"
        f"🌐 Network: <b>BSC (BEP20)</b>\n"
        f"📥 Send to:\n<code>{result['address']}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚠️ <b>Only USDT on BEP20 (BSC) network!</b>\n"
        f"⚠️ Wrong network = lost funds.\n\n"
        f"After sending, paste your <b>TX hash</b> here:"
    )
    await update.message.reply_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="sponsor:cancel")]
        ]),
        disable_web_page_preview=True,
    )
    context.user_data["awaiting_deposit_txhash"] = result["deposit_id"]


async def _dispatch_xrocket(update, context, session, sponsor, amount):
    from services.sponsor_service import SponsorService
    try:
        result = await SponsorService.create_xrocket_deposit_invoice(
            session, sponsor.id, amount
        )
        await session.commit()
    except Exception as e:
        log.exception("xRocket invoice failed")
        await update.message.reply_text(f"❌ Failed: {str(e)[:200]}")
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Pay Now", url=result["pay_url"])],
        [InlineKeyboardButton(
            "🔄 Check Status",
            callback_data=f"deposit_check:{result['deposit_id']}"
        )],
        [InlineKeyboardButton("❌ Cancel", callback_data="sponsor:cancel")],
    ])
    await update.message.reply_text(
        f"✅ <b>X Rocket Invoice</b>\n\n"
        f"💵 Amount: <b>{amount} USDT</b>\n"
        f"🧾 Invoice: <code>{result['invoice_id']}</code>\n\n"
        f"⏱ Expires in 1 hour.",
        parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True,
    )


async def handle_deposit_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check xRocket invoice status manually."""
    query = update.callback_query
    await query.answer("⏳ Checking...")

    deposit_id = int(query.data.split(":")[1])

    from models.deposit import Deposit, DepositStatus
    from services.sponsor_service import SponsorService
    from services.xrocket_service import XRocketService, XRocketError

    async with get_session() as session:
        dep = await session.get(Deposit, deposit_id)
        if not dep:
            await query.answer("❌ Deposit not found", show_alert=True)
            return
        if dep.status == DepositStatus.CONFIRMED:
            await query.answer("✅ Already confirmed!", show_alert=True)
            return
        if not dep.xrocket_invoice_id:
            await query.answer("⚠️ No invoice ID", show_alert=True)
            return

        try:
            resp = await XRocketService.get_invoice(dep.xrocket_invoice_id)
        except XRocketError as e:
            await query.answer(f"❌ {e.detail[:100]}", show_alert=True)
            return

        xr_status = (resp.get("status") or "").lower()
        if xr_status in ("paid", "finished", "completed"):
            ok = await SponsorService.confirm_xrocket_deposit(
                session, dep.id, resp
            )
            await session.commit()
            if ok:
                await query.edit_message_text(
                    f"✅ <b>Payment Received!</b>\n\n"
                    f"💵 Amount: <b>{dep.amount} USDT</b>\n"
                    f"Balance credited.",
                    parse_mode="HTML",
                )
                return

        await query.answer(f"⏳ Not paid yet. Status: {xr_status}", show_alert=True)