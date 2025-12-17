"""
app.py
Streamlit Gym Management System (owner-only).
Run: streamlit run app.py
"""

from __future__ import annotations

from datetime import date, timedelta
import pandas as pd
import streamlit as st

import db
import auth
import utils
from models import PLAN_MONTHS

st.set_page_config(page_title="Gym Management System", layout="wide")


def init_once():
    # Initialize DB + default admin if needed
    default_hash = auth.hash_password("admin123")
    db.init_db(default_hash)


def require_login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "username" not in st.session_state:
        st.session_state.username = None


def logout():
    st.session_state.logged_in = False
    st.session_state.username = None
    st.success("Logged out.")


def login_screen():
    st.title("🔐 Gym Owner Login")

    col1, col2 = st.columns([1, 1])
    with col1:
        username = st.text_input("Username", value="admin")
        password = st.text_input("Password", type="password")
        if st.button("Login", type="primary"):
            if auth.login(username.strip(), password):
                st.session_state.logged_in = True
                st.session_state.username = username.strip()
                st.rerun()
            else:
                st.error("Invalid username or password.")

    with col2:
        st.info(
            "First run creates a default admin:\n\n"
            "- username: **admin**\n"
            "- password: **admin123**\n\n"
            "You will be forced to change it on first login."
        )


def force_change_password_screen():
    st.title("⚠️ Change Password (Required)")

    st.warning("You must change the default password before using the app.")
    new1 = st.text_input("New password", type="password")
    new2 = st.text_input("Confirm new password", type="password")

    if st.button("Update password", type="primary"):
        if len(new1) < 6:
            st.error("Password must be at least 6 characters.")
            return
        if new1 != new2:
            st.error("Passwords do not match.")
            return
        auth.change_password(st.session_state.username, new1)
        st.success("Password updated. You can continue.")
        st.rerun()


# ---------- Data access helpers ----------

def fetch_members(search: str = "", status_filter: str = "All", sort_end_date: bool = True):
    sql = "SELECT * FROM members WHERE 1=1"
    params = []

    if search.strip():
        sql += " AND (full_name LIKE ? OR phone LIKE ?)"
        like = f"%{search.strip()}%"
        params.extend([like, like])

    if status_filter in ("active", "expired"):
        sql += " AND status = ?"
        params.append(status_filter)

    if sort_end_date:
        sql += " ORDER BY end_date ASC"
    else:
        sql += " ORDER BY id DESC"

    return db.fetch_all(sql, tuple(params))


def refresh_member_statuses():
    # Keep statuses consistent with end_date
    rows = db.fetch_all("SELECT id, end_date FROM members")
    for r in rows:
        status = utils.infer_status(r["end_date"])
        db.execute("UPDATE members SET status = ? WHERE id = ?", (status, r["id"]))


def dashboard_page():
    st.header("📊 Dashboard")

    refresh_member_statuses()

    total_active = db.fetch_one("SELECT COUNT(*) AS c FROM members WHERE status='active'")["c"]

    today = date.today()
    in_7 = (today + timedelta(days=7)).isoformat()
    expiring_soon = db.fetch_one(
        "SELECT COUNT(*) AS c FROM members WHERE status='active' AND end_date BETWEEN ? AND ?",
        (today.isoformat(), in_7),
    )["c"]

    month_start = today.replace(day=1).isoformat()
    month_end = (today.replace(day=28) + timedelta(days=4)).replace(day=1).isoformat()  # next month start
    monthly_rev = db.fetch_one(
        "SELECT COALESCE(SUM(amount),0) AS s FROM payments WHERE date >= ? AND date < ?",
        (month_start, month_end),
    )["s"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Total active members", int(total_active))
    c2.metric("Expiring in next 7 days", int(expiring_soon))
    c3.metric("Monthly revenue (current month)", f"{float(monthly_rev):.2f}")

    st.divider()

    st.subheader("Expiring soon (next 7 days)")
    rows = db.fetch_all(
        """
        SELECT id, full_name, phone, end_date
        FROM members
        WHERE status='active' AND end_date BETWEEN ? AND ?
        ORDER BY end_date ASC
        """,
        (today.isoformat(), in_7),
    )
    if rows:
        st.dataframe(pd.DataFrame([dict(r) for r in rows]), use_container_width=True)
    else:
        st.caption("No members expiring in the next 7 days.")


def member_form(existing=None):
    if existing:
        st.subheader(f"✏️ Edit Member (ID: {existing['id']})")
    else:
        st.subheader("➕ Add Member")

    col1, col2, col3 = st.columns(3)
    with col1:
        full_name = st.text_input("Full name", value=(existing["full_name"] if existing else ""))
        phone = st.text_input("Phone", value=(existing["phone"] if existing else ""))
        national_id = st.text_input("National ID (optional)", value=(existing["national_id"] if existing else ""))

    with col2:
        join_date = st.date_input(
            "Join date", value=(utils.parse_iso(existing["join_date"]) if existing else date.today())
        ).isoformat()

        plan_type = st.selectbox(
            "Plan type",
            options=list(PLAN_MONTHS.keys()),
            index=(list(PLAN_MONTHS.keys()).index(existing["plan_type"]) if existing else 0),
        )
        plan_price = st.text_input("Plan price", value=(str(existing["plan_price"]) if existing else "300"))

    with col3:
        start_date = st.date_input(
            "Start date", value=(utils.parse_iso(existing["start_date"]) if existing else date.today())
        ).isoformat()

        auto_end = utils.calc_end_date(start_date, plan_type)
        end_date = st.date_input(
            "End date (auto-calculated, editable)",
            value=(utils.parse_iso(existing["end_date"]) if existing else utils.parse_iso(auto_end)),
        ).isoformat()

        status = st.selectbox(
            "Status",
            options=["active", "expired"],
            index=(0 if (existing and existing["status"] == "active") or (not existing) else 1),
        )

    # If user keeps status "active" but end date already passed, we still allow but suggest
    errors = utils.validate_member_inputs(full_name, phone, plan_price, start_date, end_date)
    if errors:
        for e in errors:
            st.error(e)

    submitted = st.button("Save", type="primary", disabled=bool(errors))

    if submitted:
        nat = national_id.strip() or None
        price = float(plan_price)
        # status can be inferred, but allow manual override
        if existing:
            db.execute(
                """
                UPDATE members SET full_name=?, phone=?, national_id=?, join_date=?,
                    plan_type=?, plan_price=?, start_date=?, end_date=?, status=?
                WHERE id=?
                """,
                (full_name.strip(), phone.strip(), nat, join_date, plan_type, price, start_date, end_date, status, existing["id"]),
            )
            st.success("Member updated.")
        else:
            db.execute(
                """
                INSERT INTO members(full_name, phone, national_id, join_date, plan_type, plan_price, start_date, end_date, status)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (full_name.strip(), phone.strip(), nat, join_date, plan_type, price, start_date, end_date, status),
            )
            st.success("Member added.")
        st.rerun()


def members_page():
    st.header("👥 Members")

    refresh_member_statuses()

    with st.sidebar:
        st.subheader("Search & Filters")
        search = st.text_input("Search (name/phone)")
        status_filter = st.selectbox("Status", ["All", "active", "expired"])
        sort_end = st.checkbox("Sort by end_date", value=True)

    rows = fetch_members(search=search, status_filter=status_filter, sort_end_date=sort_end)
    df = pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame(columns=[
        "id","full_name","phone","national_id","join_date","plan_type","plan_price","start_date","end_date","status"
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()

    colA, colB = st.columns([1, 2])
    with colA:
        st.subheader("Select member")
        member_ids = df["id"].tolist() if not df.empty else []
        selected_id = st.selectbox("Member ID", options=["(none)"] + [str(i) for i in member_ids])

    with colB:
        if selected_id != "(none)":
            m = db.fetch_one("SELECT * FROM members WHERE id = ?", (int(selected_id),))
            st.subheader("Member actions")
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("Edit"):
                    st.session_state.edit_member_id = int(selected_id)
                    st.rerun()
            with c2:
                if st.button("View payments"):
                    st.session_state.payments_member_id = int(selected_id)
                    st.session_state.page = "Payments"
                    st.rerun()
            with c3:
                delete_confirm = st.checkbox("Confirm delete", value=False, key="del_confirm")
                if st.button("Delete", type="secondary", disabled=not delete_confirm):
                    db.execute("DELETE FROM members WHERE id = ?", (int(selected_id),))
                    st.success("Member deleted.")
                    st.rerun()

    st.divider()

    if st.session_state.get("edit_member_id"):
        existing = db.fetch_one("SELECT * FROM members WHERE id = ?", (st.session_state.edit_member_id,))
        if existing:
            member_form(existing=existing)
        if st.button("Cancel edit"):
            st.session_state.edit_member_id = None
            st.rerun()
    else:
        member_form(existing=None)


def payments_page():
    st.header("💳 Payments")

    refresh_member_statuses()

    members = db.fetch_all("SELECT id, full_name, phone FROM members ORDER BY full_name ASC")
    if not members:
        st.info("No members yet. Add a member first.")
        return

    default_member_id = st.session_state.get("payments_member_id", members[0]["id"])
    options = {f"{m['full_name']} ({m['phone']}) - ID {m['id']}": m["id"] for m in members}
    label_list = list(options.keys())
    default_index = label_list.index(next(k for k, v in options.items() if v == default_member_id)) if default_member_id in options.values() else 0
    chosen_label = st.selectbox("Member", label_list, index=default_index)
    member_id = options[chosen_label]
    st.session_state.payments_member_id = member_id

    st.subheader("Add payment")
    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    with c1:
        amount = st.text_input("Amount", value="300")
    with c2:
        pay_date = st.date_input("Date", value=date.today()).isoformat()
    with c3:
        method = st.selectbox("Method", ["cash", "card", "transfer"])
    with c4:
        notes = st.text_input("Notes", value="")

    if st.button("Record payment", type="primary"):
        try:
            amt = float(amount)
            if amt <= 0:
                st.error("Amount must be > 0.")
            else:
                db.execute(
                    "INSERT INTO payments(member_id, amount, date, method, notes) VALUES(?,?,?,?,?)",
                    (member_id, amt, pay_date, method, notes.strip() or None),
                )
                st.success("Payment recorded.")
                st.rerun()
        except Exception:
            st.error("Amount must be numeric.")

    st.divider()

    st.subheader("Payment history")
    rows = db.fetch_all(
        """
        SELECT p.id, p.member_id, p.amount, p.date, p.method, p.notes
        FROM payments p
        WHERE p.member_id=?
        ORDER BY p.date DESC, p.id DESC
        """,
        (member_id,),
    )
    if rows:
        st.dataframe(pd.DataFrame([dict(r) for r in rows]), use_container_width=True, hide_index=True)
    else:
        st.caption("No payments for this member yet.")


def renewals_page():
    st.header("🔁 Renewals (One-click)")

    refresh_member_statuses()

    members = db.fetch_all("SELECT id, full_name, phone, plan_type, plan_price, end_date FROM members ORDER BY full_name ASC")
    if not members:
        st.info("No members yet.")
        return

    options = {f"{m['full_name']} ({m['phone']}) - ID {m['id']}": m["id"] for m in members}
    chosen_label = st.selectbox("Member", list(options.keys()))
    member_id = options[chosen_label]
    m = db.fetch_one("SELECT * FROM members WHERE id = ?", (member_id,))

    st.write(f"Current plan: **{m['plan_type']}** | Price: **{m['plan_price']}** | End: **{m['end_date']}** | Status: **{m['status']}**")

    col1, col2, col3 = st.columns(3)
    with col1:
        plan_type = st.selectbox("New plan type", options=list(PLAN_MONTHS.keys()), index=list(PLAN_MONTHS.keys()).index(m["plan_type"]))
    with col2:
        plan_price = st.text_input("New plan price", value=str(m["plan_price"]))
    with col3:
        # Default start date: today (or day after current end if still active and end_date >= today)
        current_end = utils.parse_iso(m["end_date"])
        default_start = date.today()
        if current_end >= date.today():
            default_start = current_end + timedelta(days=1)
        start_date = st.date_input("Start date", value=default_start).isoformat()

    end_date = utils.calc_end_date(start_date, plan_type)
    st.info(f"Auto-calculated end date: **{end_date}**")

    record_payment = st.toggle("Record payment now", value=True)
    pay_method = st.selectbox("Payment method", ["cash", "card", "transfer"], disabled=not record_payment)
    pay_notes = st.text_input("Payment notes", value="", disabled=not record_payment)

    if st.button("Renew", type="primary"):
        errors = utils.validate_member_inputs(m["full_name"], m["phone"], plan_price, start_date, end_date)
        if errors:
            for e in errors:
                st.error(e)
            return

        price = float(plan_price)
        status = utils.infer_status(end_date)
        db.execute(
            """
            UPDATE members
            SET plan_type=?, plan_price=?, start_date=?, end_date=?, status=?
            WHERE id=?
            """,
            (plan_type, price, start_date, end_date, status, member_id),
        )

        if record_payment:
            db.execute(
                "INSERT INTO payments(member_id, amount, date, method, notes) VALUES(?,?,?,?,?)",
                (member_id, price, date.today().isoformat(), pay_method, pay_notes.strip() or None),
            )

        st.success("Renewal completed.")
        st.rerun()


def reports_page():
    st.header("🧾 Reports")

    refresh_member_statuses()

    st.subheader("Export members to CSV")
    members = db.fetch_all("SELECT * FROM members ORDER BY id DESC")
    if members:
        st.download_button(
            "Download members.csv",
            data=utils.members_to_csv_bytes(members),
            file_name="members.csv",
            mime="text/csv",
        )
    else:
        st.caption("No members to export.")

    st.divider()

    st.subheader("Export payments to CSV")
    payments = db.fetch_all(
        """
        SELECT p.id, p.member_id, m.full_name, p.amount, p.date, p.method, p.notes
        FROM payments p
        JOIN members m ON m.id = p.member_id
        ORDER BY p.date DESC, p.id DESC
        """
    )
    if payments:
        st.download_button(
            "Download payments.csv",
            data=utils.payments_to_csv_bytes(payments),
            file_name="payments.csv",
            mime="text/csv",
        )
    else:
        st.caption("No payments to export.")

    st.divider()

    st.subheader("Revenue summary by month")
    df = utils.revenue_summary_by_month()
    st.dataframe(df, use_container_width=True, hide_index=True)


def reminders_page():
    st.header("⏰ Expiring Soon (Next 7 days)")

    refresh_member_statuses()

    today = date.today()
    in_7 = (today + timedelta(days=7)).isoformat()
    rows = db.fetch_all(
        """
        SELECT id, full_name, phone, end_date
        FROM members
        WHERE status='active' AND end_date BETWEEN ? AND ?
        ORDER BY end_date ASC
        """,
        (today.isoformat(), in_7),
    )

    if rows:
        st.dataframe(pd.DataFrame([dict(r) for r in rows]), use_container_width=True, hide_index=True)
    else:
        st.caption("No expiring-soon members.")


def settings_page():
    st.header("⚙️ Settings")

    st.subheader("Change password")
    p1 = st.text_input("New password", type="password")
    p2 = st.text_input("Confirm new password", type="password")
    if st.button("Update password", type="primary"):
        if len(p1) < 6:
            st.error("Password must be at least 6 characters.")
        elif p1 != p2:
            st.error("Passwords do not match.")
        else:
            auth.change_password(st.session_state.username, p1)
            st.success("Password updated.")

    st.divider()

    st.subheader("Sample data")
    st.caption("Insert 3 sample members + a few payments for testing (adds new rows each run).")
    if st.button("Insert sample data"):
        utils.insert_sample_data()
        st.success("Sample data inserted.")
        st.rerun()


def main_app():
    st.sidebar.title("🏋️ Gym System")
    st.sidebar.caption(f"Logged in as: {st.session_state.username}")

    pages = ["Dashboard", "Members", "Payments", "Renewals", "Reports", "Reminders", "Settings"]
    if "page" not in st.session_state:
        st.session_state.page = "Dashboard"
    st.session_state.page = st.sidebar.radio("Navigate", pages, index=pages.index(st.session_state.page))

    if st.sidebar.button("Logout"):
        logout()
        st.rerun()

    if st.session_state.page == "Dashboard":
        dashboard_page()
    elif st.session_state.page == "Members":
        members_page()
    elif st.session_state.page == "Payments":
        payments_page()
    elif st.session_state.page == "Renewals":
        renewals_page()
    elif st.session_state.page == "Reports":
        reports_page()
    elif st.session_state.page == "Reminders":
        reminders_page()
    elif st.session_state.page == "Settings":
        settings_page()


# --------- App entry ---------

def run():
    init_once()
    require_login()

    if not st.session_state.logged_in:
        login_screen()
        return

    # Force password change on first login after DB creation
    if db.is_force_password_change():
        force_change_password_screen()
        return

    main_app()


if __name__ == "__main__":
    run()
