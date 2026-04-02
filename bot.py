import logging
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, TypeHandler, filters
from telegram.ext import ApplicationHandlerStop
from telegram.error import TimedOut, NetworkError, RetryAfter, Conflict

from config import BOT_TOKEN
from rw_bot import ReplBot
from db import (init_db, seed_game_services,
                update_balance, add_balance, get_balance, get_referrer, get_ref_percent,
                is_invoice_processed, mark_invoice_processed,
                _migrate_usernames, _migrate_cards, seed_stc_packages,
                _migrate_vip_offers, backfill_total_spent)

from handlers.start   import start_handler
from handlers.menu    import menu_handler
from handlers.gsm import (
    gsm_conv,
    gsm_handler, premium_handler, stars_handler,
    rush_menu_handler, rush_members_handler,
    rush_premium_members_handler,
    rush_likes_handler, rush_views_handler,
    tgl_numbers_handler,
    confirm_buy_handler,
    digital_collectibles_handler,
)
from handlers.usernames import (
    usernames_conv, usernames_shop_handler,
    uname_confirm_handler, uname_cancel_handler,
)
from handlers.general  import general_handler, netflix_handler, netflix_conv
from handlers.services import (
    services_menu_handler, telegram_services_handler,
    back_main_handler, soon_handler,
)
from handlers.support import (
    support_conv, admin_reply_conv,
    support_menu_handler, my_tickets_handler, ticket_detail_handler,
    admin_close_handler, noop_handler,
)
from handlers.payments import (deposit_handler, deposit_conv,
                                dep_ok_handler, dep_no_handler,
                                dep_stars_menu_handler, dep_stars_invoice_handler,
                                dep_stars_precheckout, dep_stars_success_handler,
                                stars_custom_conv)
from handlers.vip import (
    vip_status_handler, daily_offers_handler,
    admin_vip_handler, admin_offers_mgr_handler,
    offer_toggle_handler, offer_del_handler, offers_delall_handler,
    add_offer_conv, edit_vip_conv,
)
from handlers.orders  import (
    my_orders_handler, order_detail_handler,
    reorder_handler, reorder_by_id_handler,
    popular_services_handler,
)
from handlers.admin   import (
    admin_handler, stats_handler, addbal_cmd_handler, prices_cmd_handler,
    admin_panel_handler, admin_users_handler, admin_stats_handler,
    admin_orders_handler, admin_curr_handler,
    admin_unames_handler, admin_cpns_handler, admin_prices_handler,
    list_unames_handler, del_uname_handler,
    list_cpns_handler, del_cpn_handler,
    done_handler, process_ord_handler, cancel_ord_handler,
    edit_rate_conv, find_user_conv, add_balance_conv,
    add_username_conv, add_coupon_conv,
    edit_price_conv, edit_ui_conv, admin_ui_handler,
    change_word_conv, search_word_conv, del_word_conv,
    admin_words_handler, list_words_handler, del_word_handler,
    admin_maintenance_handler,
    admin_agents_handler, ag_prices_handler, ag_delprice_handler,
    add_agent_conv, remove_agent_conv, agent_price_conv, agent_charge_conv,
    edit_ref_conv, admin_ref_handler,
    admin_cards_handler, admin_risk_handler, admin_reset_risk_hndlr,
    edit_card_rate_conv,
    wd_approve_conv,
    wd_reject_handler, wd_reject_pending_handler,
    review_dismiss_handler,
    setgroup_handler, unsetgroup_handler,
    cust_stmt_cb_handler, cust_stmt_msg_handler, stmt_page_handler,
    admin_assistant_handler, asst_api_conv, asst_session_conv,
    frag_done_handler, frag_refund_handler,
    sawa_manual_start_handler, sawa_amount_msg_handler, sawa_manual_rej_handler,
    admin_balances_handler, balances_page_handler,
)
from handlers.broadcast import broadcast_conv
from handlers.stc import stc_conv, stc_menu_handler, stc_page_handler, stc_back_handler
from handlers.cards import (
    cards_conv,
    admin_card_approve_handler, admin_card_custom_handler,
    admin_card_reject_handler, admin_card_custom_msg_handler,
    card_history_handler,
)
from handlers.referral  import referral_handler
from handlers.agent import agent_panel_handler, agent_conv
from handlers.ai_handler import (
    ai_toggle_handler, ai_text_handler,
    admin_ai_conv, admin_ai_suspicious_handler,
)
from handlers.reply_kb import (
    add_rb_conv, admin_rb_handler, list_rb_handler,
    del_rb_handler, custom_btn_handler,
)
from handlers.btn_colors import (
    admin_btn_colors_handler,
    bedit_section_handler, bedit_pick_handler,
    bedit_color_handler, bedit_delemoji_handler, bedit_reset_handler,
    edit_btn_conv,
)
from handlers.games import (
    games_menu, game_packages,
    game_buy_conv, game_admin_conv,
    admin_games_cb, admin_game_cat_cb,
)
from handlers.direct_pay import (
    direct_pay_conv, dp_confirm_handler, dp_reject_handler,
)
from handlers.warnings import warn_conv
from handlers.settings import (
    open_settings_handler, view_terms_handler,
    accept_terms_handler, my_info_handler,
    my_account_stmt_handler, stmt_page_user_handler,
)
from telegram.ext import CallbackQueryHandler as CQH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)


async def global_ban_check(update: Update, ctx):
    """يمنع المستخدمين المحظورين من التفاعل مع البوت."""
    if not update.effective_user:
        return
    from db import is_banned
    if is_banned(update.effective_user.id):
        if update.message:
            await update.message.reply_text("🚫 حسابك محظور. تواصل مع الدعم.")
        elif update.callback_query:
            await update.callback_query.answer("🚫 حسابك محظور", show_alert=True)
        raise ApplicationHandlerStop


async def refresh_user_info(update: Update, ctx):
    """يحدّث اسم المستخدم ويوزرنيمه في قاعدة البيانات عند كل تفاعل."""
    user = update.effective_user
    if not user:
        return
    from db import add_user
    add_user(user.id, user.username or "", user.first_name or "")


async def maintenance_check(update: Update, ctx):
    """يمنع وصول المستخدمين أثناء الصيانة (الأدمن مستثنى)."""
    from db import is_maintenance
    from config import ADMIN_ID
    if not is_maintenance():
        return
    user = update.effective_user
    if not user or user.id == ADMIN_ID:
        return
    msg = "🚧 المتجر تحت الصيانة حالياً، سنعود قريباً!"
    if update.message:
        await update.message.reply_text(msg)
    elif update.callback_query:
        await update.callback_query.answer(msg, show_alert=True)
    raise ApplicationHandlerStop


async def _crypto_checker(app: Application):
    """مهمة خلفية: تتحقق من مدفوعات CryptoPay كل 10 ثوانٍ وتشحن الرصيد تلقائياً."""
    import cryptopay as CP
    await asyncio.sleep(5)   # انتظار بسيط بعد بدء البوت
    while True:
        try:
            invoices = await CP.get_paid_invoices()
            for inv in invoices:
                iid = str(inv.invoice_id)
                if is_invoice_processed(iid):
                    continue

                payload = getattr(inv, "payload", "") or ""
                parts   = payload.split("|")
                if len(parts) != 2:
                    mark_invoice_processed(iid)
                    continue

                uid        = int(parts[0])
                amount_usd = float(parts[1])
                asset      = getattr(inv, "asset", "USDT")

                add_balance(uid, amount_usd, f"شحن عبر CryptoPay ({asset})", "إيداع")
                mark_invoice_processed(iid)

                # عمولة الإحالة
                referrer = get_referrer(uid)
                if referrer and referrer != uid:
                    pct = get_ref_percent()
                    com = round(amount_usd * pct / 100, 6)
                    if com > 0:
                        add_balance(referrer, com,
                                    f"عمولة إحالة — شحن CryptoPay ({asset})",
                                    "عمولة")
                        try:
                            await app.bot.send_message(
                                chat_id=referrer,
                                text=(
                                    f"🎉 <b>تم إضافة عمولة إحالة!</b>\n\n"
                                    f"💰 <b>+{com:.4f}$</b> ({pct:.1f}%)\n"
                                    f"من شحن أحد مستخدميك 🌹"
                                ),
                                parse_mode="HTML"
                            )
                        except Exception as notify_err:
                            logging.warning(f"فشل إرسال إشعار عمولة → {referrer}: {notify_err}")
                elif referrer == uid:
                    logging.warning(f"self-referral مُتجاهَل: uid={uid}")

                # إشعار المستخدم
                try:
                    await app.bot.send_message(
                        uid,
                        f"✅ <b>تم شحن رصيدك!</b>\n\n"
                        f"💰 <b>{amount_usd:.4f}$</b> عبر {asset} — CryptoPay",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

        except Exception as e:
            logging.warning("CryptoPay checker error: %s", e)

        await asyncio.sleep(10)


async def _post_init(app: Application):
    """يُشغَّل بعد بدء الـ Application مباشرةً."""
    from config import ADMIN_ID
    asyncio.create_task(_crypto_checker(app))
    # تهيئة الحساب المساعد (Telethon) + طابور سوا
    from assistant import init_assistant, health_check_worker
    from queue_system import queue_worker
    ok = await init_assistant()
    if ok:
        asyncio.create_task(queue_worker(app.bot))
        logging.info("✅ الحساب المساعد وطابور السوا جاهزان")
    else:
        asyncio.create_task(queue_worker(app.bot))
        logging.warning("⚠️ الحساب المساعد غير مُعدّ — الطابور يعمل بالوضع اليدوي")
    # فاحص صحة الحساب المساعد كل 5 دقائق
    asyncio.create_task(health_check_worker(app.bot, ADMIN_ID, interval=300))
    # طابور Fragment (نجوم + بريميوم تلقائي)
    from fragment_queue import fragment_worker
    from fragment import is_fragment_ready
    asyncio.create_task(fragment_worker(app.bot))
    if is_fragment_ready():
        logging.info("✅ طابور Fragment جاهز (جلسة موجودة)")
    else:
        logging.warning("⚠️ Fragment غير مُعدّ — الطلبات ستُحال يدوياً حتى ربط المحفظة")


def main():
    init_db()
    _migrate_usernames()
    _migrate_cards()
    _migrate_vip_offers()
    seed_game_services()
    seed_stc_packages()
    backfill_total_spent()

    app = (
        Application.builder()
        .bot(ReplBot(token=BOT_TOKEN))
        .post_init(_post_init)
        .build()
    )

    # ── Middleware (يشتغل قبل كل شيء) ───────────────
    app.add_handler(TypeHandler(Update, refresh_user_info),  group=-11)
    app.add_handler(TypeHandler(Update, global_ban_check),   group=-10)
    app.add_handler(TypeHandler(Update, maintenance_check),  group=-9)

    # ── /start يعمل دائماً حتى أثناء المحادثات ──────
    app.add_handler(start_handler, group=-8)

    # ── ConversationHandlers (أولاً لأنها ذات أولوية) ──
    app.add_handler(game_buy_conv)
    app.add_handler(game_admin_conv)
    app.add_handler(support_conv)
    app.add_handler(admin_reply_conv)
    app.add_handler(gsm_conv)
    app.add_handler(netflix_conv)
    app.add_handler(deposit_conv)
    app.add_handler(edit_rate_conv)
    app.add_handler(find_user_conv)
    app.add_handler(add_balance_conv)
    app.add_handler(broadcast_conv)
    app.add_handler(add_username_conv)
    app.add_handler(add_coupon_conv)
    app.add_handler(edit_price_conv)
    app.add_handler(edit_ui_conv)
    app.add_handler(change_word_conv)
    app.add_handler(search_word_conv)
    app.add_handler(del_word_conv)
    app.add_handler(add_rb_conv)
    app.add_handler(edit_btn_conv)
    app.add_handler(direct_pay_conv)
    app.add_handler(warn_conv)
    app.add_handler(add_agent_conv)
    app.add_handler(remove_agent_conv)
    app.add_handler(agent_price_conv)
    app.add_handler(agent_charge_conv)
    app.add_handler(edit_ref_conv)
    app.add_handler(admin_ai_conv)

    # ── أوامر ───────────────────────────────────────
    app.add_handler(admin_handler)
    app.add_handler(stats_handler)
    app.add_handler(addbal_cmd_handler)
    app.add_handler(prices_cmd_handler)

    # ── Callback Queries — الطلبات (قبل menu_handler) ─
    app.add_handler(my_orders_handler)
    app.add_handler(order_detail_handler)
    app.add_handler(reorder_handler)
    app.add_handler(reorder_by_id_handler)
    app.add_handler(popular_services_handler)

    # ── AI Handler ──────────────────────────────────
    app.add_handler(ai_toggle_handler)
    app.add_handler(admin_ai_suspicious_handler)
    # رسائل نصية حرة (أولوية منخفضة — بعد كل ConversationHandlers)
    app.add_handler(ai_text_handler, group=10)

    # ── الإعدادات + الشروط ──────────────────────────
    app.add_handler(accept_terms_handler)
    app.add_handler(open_settings_handler)
    app.add_handler(view_terms_handler)
    app.add_handler(my_info_handler)
    app.add_handler(my_account_stmt_handler)
    app.add_handler(stmt_page_user_handler)

    # ── Callback Queries — القوائم ─────────────────
    app.add_handler(referral_handler)
    app.add_handler(agent_conv)
    app.add_handler(agent_panel_handler)
    app.add_handler(menu_handler)
    app.add_handler(services_menu_handler)
    app.add_handler(telegram_services_handler)
    app.add_handler(tgl_numbers_handler)
    app.add_handler(confirm_buy_handler)
    app.add_handler(back_main_handler)
    app.add_handler(soon_handler)
    app.add_handler(premium_handler)
    app.add_handler(stars_handler)
    app.add_handler(rush_menu_handler)
    app.add_handler(rush_members_handler)
    app.add_handler(rush_premium_members_handler)
    app.add_handler(rush_likes_handler)
    app.add_handler(rush_views_handler)
    app.add_handler(digital_collectibles_handler)
    # ── متجر اليوزرات ───────────────────────────
    app.add_handler(usernames_conv)
    app.add_handler(usernames_shop_handler)
    app.add_handler(uname_confirm_handler)
    app.add_handler(uname_cancel_handler)
    app.add_handler(general_handler)
    app.add_handler(netflix_handler)
    app.add_handler(deposit_handler)
    app.add_handler(dep_ok_handler)
    app.add_handler(dep_no_handler)
    app.add_handler(dp_confirm_handler)
    app.add_handler(dp_reject_handler)
    app.add_handler(stars_custom_conv)
    app.add_handler(dep_stars_menu_handler)
    app.add_handler(dep_stars_invoice_handler)
    app.add_handler(dep_stars_precheckout)
    app.add_handler(dep_stars_success_handler, group=5)
    # ── VIP + عروض يومية ─────────────────────────
    app.add_handler(edit_vip_conv)
    app.add_handler(add_offer_conv)
    app.add_handler(vip_status_handler)
    app.add_handler(daily_offers_handler)
    app.add_handler(admin_vip_handler)
    app.add_handler(admin_offers_mgr_handler)
    app.add_handler(offer_toggle_handler)
    app.add_handler(offer_del_handler)
    app.add_handler(offers_delall_handler)
    # ── الألعاب ──────────────────────────────────
    app.add_handler(CQH(games_menu,      pattern=r"^games$"))
    app.add_handler(CQH(game_packages,   pattern=r"^game_cat_"))

    # ── Admin Panel ──────────────────────────────────
    app.add_handler(admin_panel_handler)
    app.add_handler(admin_users_handler)
    app.add_handler(admin_stats_handler)
    app.add_handler(admin_orders_handler)
    app.add_handler(admin_balances_handler)
    app.add_handler(balances_page_handler)
    app.add_handler(admin_curr_handler)
    app.add_handler(admin_unames_handler)
    app.add_handler(admin_cpns_handler)
    app.add_handler(admin_prices_handler)
    app.add_handler(list_unames_handler)
    app.add_handler(del_uname_handler)
    app.add_handler(list_cpns_handler)
    app.add_handler(del_cpn_handler)
    app.add_handler(support_menu_handler)
    app.add_handler(my_tickets_handler)
    app.add_handler(ticket_detail_handler)
    app.add_handler(admin_close_handler)
    app.add_handler(noop_handler)
    app.add_handler(done_handler)
    app.add_handler(process_ord_handler)
    app.add_handler(cancel_ord_handler)
    app.add_handler(admin_ui_handler)
    app.add_handler(admin_words_handler)
    app.add_handler(list_words_handler)
    app.add_handler(del_word_handler)
    app.add_handler(admin_maintenance_handler)
    app.add_handler(admin_agents_handler)
    app.add_handler(ag_prices_handler)
    app.add_handler(ag_delprice_handler)
    app.add_handler(CQH(admin_games_cb,    pattern=r"^admin_games$"))
    app.add_handler(CQH(admin_game_cat_cb, pattern=r"^admin_gcat_"))
    app.add_handler(admin_rb_handler)
    app.add_handler(list_rb_handler)
    app.add_handler(del_rb_handler)
    app.add_handler(custom_btn_handler)
    app.add_handler(admin_btn_colors_handler)
    app.add_handler(bedit_section_handler)
    app.add_handler(bedit_pick_handler)
    app.add_handler(bedit_color_handler)
    app.add_handler(bedit_delemoji_handler)
    app.add_handler(bedit_reset_handler)
    # ── STC باقات ────────────────────────────────
    app.add_handler(stc_conv)
    app.add_handler(stc_menu_handler)
    app.add_handler(stc_page_handler)
    app.add_handler(stc_back_handler)
    # ── شحن بطاقات ──────────────────────────────
    app.add_handler(cards_conv)
    app.add_handler(card_history_handler)
    app.add_handler(admin_card_approve_handler)
    app.add_handler(admin_card_custom_handler)
    app.add_handler(admin_card_reject_handler)
    # ── إدارة البطاقات (أدمن) ─────────────────
    app.add_handler(edit_card_rate_conv)
    app.add_handler(admin_cards_handler)
    app.add_handler(admin_risk_handler)
    app.add_handler(admin_reset_risk_hndlr)
    app.add_handler(admin_ref_handler)
    app.add_handler(admin_card_custom_msg_handler)
    # ── موافقة السحب ─────────────────────────────
    app.add_handler(wd_approve_conv)
    app.add_handler(wd_reject_handler)
    app.add_handler(wd_reject_pending_handler, group=-2)
    app.add_handler(review_dismiss_handler)
    # ── مجموعة الطلبات ───────────────────────────
    app.add_handler(setgroup_handler)
    app.add_handler(unsetgroup_handler)
    app.add_handler(cust_stmt_cb_handler)
    app.add_handler(stmt_page_handler)
    app.add_handler(cust_stmt_msg_handler, group=-1)
    # ── الحساب المساعد (Telethon / @stc25bot) ──────
    app.add_handler(asst_api_conv)
    app.add_handler(asst_session_conv)
    app.add_handler(admin_assistant_handler)
    app.add_handler(frag_done_handler)
    app.add_handler(frag_refund_handler)

    # ── شحن سوا اليدوي ──
    app.add_handler(sawa_manual_start_handler)
    app.add_handler(sawa_manual_rej_handler)
    app.add_handler(sawa_amount_msg_handler, group=-3)

    # ── معالج الأخطاء العالمي ────────────────────────
    async def error_handler(update, context):
        err = context.error
        if isinstance(err, TimedOut):
            logging.warning("⚠️ TimedOut — سيعيد المحاولة تلقائياً")
            return
        if isinstance(err, RetryAfter):
            logging.warning(f"⚠️ RetryAfter {err.retry_after}s — الإرسال مؤجل")
            return
        if isinstance(err, (NetworkError, Conflict)):
            logging.warning(f"⚠️ {type(err).__name__}: {err}")
            return
        logging.exception(f"❌ خطأ غير متوقع: {err}", exc_info=err)

    app.add_error_handler(error_handler)

    logging.info("🤖 البوت يعمل الآن...")
    app.run_polling(
        drop_pending_updates=True,
        timeout=60,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()
