from calendar import month_abbr
from datetime import datetime
import os
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename

from .staff_form import ForgotPasswordForm
from .models import FinancialGoal, Loan, SavingMode, Transaction, User, Account, db
from .forms import LoginForm, DepositForm, SetGoalForm, WithdrawForm, TransferForm, ProfileForm
import base64, numpy as np
from io import BytesIO
from PIL import Image
import cv2

main = Blueprint("main", __name__)

from functools import wraps
from flask import make_response

def nocache(view):
    @wraps(view)
    def no_cache(*args, **kwargs):
        response = make_response(view(*args, **kwargs))
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "-1"
        return response
    return no_cache

# ---------------------- Utilities ---------------------- #
def get_face_encoding(image_array):
    gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
    resized = cv2.resize(gray, (100, 100))
    return resized.flatten() / 255.0

def get_or_create_account(user):
    if hasattr(user, "account") and user.account:
        return user.account
    account = Account(user_id=user.id, balance=0.0)
    db.session.add(account)
    db.session.commit()
    return account

# ---------------------- Root ---------------------- #
@main.route("/")
def home():
    return render_template("home.html")


from flask import render_template, redirect, url_for, flash
from flask_login import login_user
from .forms import LoginForm
from .models import User

@main.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()  # Create the form instance

    if form.validate_on_submit():  # Handles POST automatically
        email = form.email.data
        password = form.password.data

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            flash("Login successful!", "success")
            return redirect(url_for("main.dashboard"))

        flash("Invalid credentials", "danger")

    # Always pass the form to the template
    return render_template("login.html", form=form)

@main.route("/face_login", methods=["POST"])
def face_login():
    face_data_url = request.form.get("face_image")
    if not face_data_url:
        flash("Face image not received", "danger")
        return redirect(url_for("main.login"))
    try:
        header, encoded = face_data_url.split(",", 1)
        img_bytes = base64.b64decode(encoded)
        img = Image.open(BytesIO(img_bytes)).convert("RGB")
        img_np = np.array(img)
        login_encoding = get_face_encoding(img_np)

        users = User.query.all()
        for user in users:
            if user.face_encoding:
                saved_encoding = np.frombuffer(user.face_encoding, dtype=np.float32)
                sim = np.dot(saved_encoding, login_encoding) / (np.linalg.norm(saved_encoding) * np.linalg.norm(login_encoding))
                if sim > 0.6:
                    login_user(user)
                    flash("Face login successful!", "success")
                    return redirect(url_for("main.dashboard"))

        flash("No matching user found", "danger")
        return redirect(url_for("main.login"))
    except Exception as e:
        flash("Face login failed", "danger")
        print("Face login error:", str(e))
        return redirect(url_for("main.login"))

@main.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out", "success")
    return redirect(url_for("main.login"))

# ---------------------- Dashboard ---------------------- #
@main.route("/dashboard")
@login_required
def dashboard():
    account = get_or_create_account(current_user)
    balance = account.balance if account else 0.0
    account_number = account.account_number if account else None
    goal_savings = sum(getattr(goal, "smart_saver_balance", 0) for goal in getattr(current_user, "goals", []))
    usable_balance = balance - goal_savings

    return render_template("dashboard.html",
                           username=current_user.username,
                           account_number=account_number,
                           balance=balance,
                           usable_balance=usable_balance,
                           goal_savings=goal_savings)
    
# ---------------------- Password ---------------------- #
@main.route("/forgot_password", methods=["GET", "POST"])
@nocache
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            user.set_password(form.new_password.data)
            db.session.commit()
            flash("Password reset successful! Please login.", "success")
            return redirect(url_for("main.login"))
        flash("No account found with that email.", "danger")
    return render_template("forgot_password.html", form=form)

# ---------------------- Transactions ---------------------- #
def process_transaction(user, txn_type, amount, recipient_account=None, description=None):
    txn = Transaction(user_id=user.id,
                      type=txn_type,
                      amount=amount,
                      recipient_account=recipient_account,
                      description=description or txn_type,
                      status="Success")
    db.session.add(txn)
    db.session.commit()

@main.route('/deposit', methods=['GET', 'POST'])
@login_required
def deposit():
    form = DepositForm()
    if form.validate_on_submit():
        amount = float(form.amount.data)
        if amount <= 0:
            flash("Enter a valid amount", "danger")
        else:
            account = get_or_create_account(current_user)
            account.balance += amount
            process_transaction(current_user, "Deposit", amount)
            flash("Deposit successful!", "success")
            return redirect(url_for('main.dashboard'))
    return render_template('deposit.html', form=form)

@main.route('/withdraw', methods=['GET', 'POST'])
@login_required
def withdraw():
    form = WithdrawForm()
    if form.validate_on_submit():
        amount = float(form.amount.data)
        account = get_or_create_account(current_user)
        if amount <= 0 or amount > account.balance:
            flash("Invalid withdrawal amount", "danger")
        else:
            account.balance -= amount
            process_transaction(current_user, "Withdraw", amount)
            flash("Withdrawal successful!", "success")
            return redirect(url_for('main.dashboard'))
    return render_template('withdraw.html', form=form)

@main.route('/transfer', methods=['GET', 'POST'])
@login_required
def transfer():
    form = TransferForm()
    if form.validate_on_submit():
        amount = float(form.amount.data)
        recipient_acc = form.recipient_account.data
        sender = get_or_create_account(current_user)
        recipient = Account.query.filter_by(account_number=recipient_acc).first()

        if not recipient:
            flash("Recipient not found", "danger")
        elif recipient.id == sender.id:
            flash("Cannot transfer to yourself", "warning")
        elif amount <= 0 or amount > sender.balance:
            flash("Invalid transfer amount", "danger")
        else:
            sender.balance -= amount
            recipient.balance += amount
            process_transaction(current_user, "Transfer", amount, recipient_account=recipient_acc)
            flash("Transfer successful!", "success")
            return redirect(url_for('main.dashboard'))
    return render_template('transfer.html', form=form)

# ---------------------- Profile ---------------------- #
@main.route("/profile", methods=["GET", "POST"])
@login_required
@nocache
def profile():
    form = ProfileForm()
    if form.validate_on_submit():
        if form.email.data != current_user.email:
            if User.query.filter_by(email=form.email.data).first():
                flash("Email already exists.", "danger")
                return redirect(url_for("main.profile"))
            current_user.email = form.email.data
        current_user.name = form.name.data
        current_user.place = form.place.data
        current_user.mobile_number = form.mobile_number.data

        if form.profile_image.data:
            filename = secure_filename(form.profile_image.data.filename)
            upload_path = os.path.join(current_app.root_path, "static/uploads", filename)
            form.profile_image.data.save(upload_path)
            current_user.profile_image = filename

        db.session.commit()
        flash("Profile updated successfully!", "success")
        return redirect(url_for("main.profile"))

    elif request.method == "GET":
        form.name.data = current_user.name
        form.place.data = current_user.place
        form.mobile_number.data = current_user.mobile_number
        form.email.data = current_user.email

    return render_template("profile.html", form=form, user=current_user)

# ---------------------- Loans ---------------------- #
@main.route("/loan", methods=["GET", "POST"])
@login_required
@nocache
def loan():
    if request.method == "POST":
        amount = request.form.get("amount")
        reason = request.form.get("reason")
        try:
            amount_float = float(amount)
            if not amount or not reason or amount_float <= 0:
                raise ValueError
            new_loan = Loan(user_id=current_user.id, amount=amount_float, reason=reason)
            db.session.add(new_loan)
            db.session.commit()
            flash("Loan application submitted successfully!", "success")
            return redirect(url_for("main.dashboard"))
        except ValueError:
            flash("Invalid input. Fill all fields correctly.", "danger")
            return redirect(url_for("main.loan"))
    return render_template("loan.html")

@main.route("/my_loans")
@login_required
@nocache
def my_loans():
    loans = Loan.query.filter_by(user_id=current_user.id).order_by(Loan.id.desc()).all()
    return render_template("my_loans.html", loans=loans)

# ---------------------- Goals ---------------------- #
@main.route("/financial_goals")
@login_required
def financial_goals_landing():
    goals = FinancialGoal.query.filter_by(user_id=current_user.id).all()
    return render_template("goal_basic.html", goals=goals)

@main.route("/goal_calculator")
@login_required
def goal_calculator():
    return render_template("goal_calculator.html")

# ---------------------- Goal Management ---------------------- #
@main.route("/view_goals")
@login_required
def view_goals():
    goals = FinancialGoal.query.filter_by(user_id=current_user.id).all()
    warnings = []

    for goal in goals:
        start = datetime.utcnow().date()
        end = goal.deadline
        labels = []
        current = start
        while current <= end:
            labels.append(month_abbr[current.month])
            current = current.replace(year=current.year + (current.month // 12), month=(current.month % 12) + 1)

        monthly_value = goal.smart_saver_balance / max(1, len(labels))
        goal.chart_labels = labels
        goal.chart_data = [round(monthly_value, 2)] * len(labels)

        days_left = (goal.deadline - datetime.utcnow().date()).days
        if days_left <= 5 and goal.smart_saver_balance < goal.target_amount:
            remaining = goal.target_amount - goal.smart_saver_balance
            warnings.append(f"⚠️ Goal '{goal.name}' is nearing deadline! ₹{remaining:.0f} left to save.")

    return render_template("view_goal.html", goals=goals, warnings=warnings)

# ---------------------- Single Goal ---------------------- #
@main.route("/goal/<int:goal_id>")
@login_required
def view_single_goal(goal_id):
    goal = FinancialGoal.query.get_or_404(goal_id)
    if goal.user_id != current_user.id:
        flash("Unauthorized access.", "danger")
        return redirect(url_for("main.view_goals"))
    goal.chart_labels = ["Jan", "Feb", "Mar", "Apr"]
    goal.chart_data = [1000, 2500, 3000, int(goal.smart_saver_balance)]
    return render_template("single_goal.html", goal=goal)

# ---------------------- Edit / Delete / Deposit ---------------------- #
@main.route("/goal/edit/<int:goal_id>", methods=["GET", "POST"])
@login_required
def edit_goal(goal_id):
    goal = FinancialGoal.query.get_or_404(goal_id)
    if goal.user_id != current_user.id:
        flash("Unauthorized access.", "danger")
        return redirect(url_for("main.view_goals"))
    if request.method == "POST":
        goal.name = request.form.get("goalName")
        goal.target_amount = float(request.form.get("goalAmount") or 0)
        goal.deadline = datetime.strptime(request.form.get("deadline"), "%Y-%m-%d").date()
        db.session.commit()
        flash("Goal updated successfully.", "success")
        return redirect(url_for("main.view_goals"))
    return render_template("edit_goal.html", goal=goal)

@main.route("/goal/delete/<int:goal_id>", methods=["POST"])
@login_required
def delete_goal(goal_id):
    goal = FinancialGoal.query.get_or_404(goal_id)
    if goal.user_id != current_user.id:
        flash("Unauthorized", "danger")
        return redirect(url_for("main.view_goals"))
    db.session.delete(goal)
    db.session.commit()
    flash("Goal deleted successfully.", "info")
    return redirect(url_for("main.view_goals"))

@main.route("/set_goal", methods=["GET", "POST"])
@login_required
def set_goal():
    form = SetGoalForm()
    if form.validate_on_submit():
        goal = FinancialGoal(
            user_id=current_user.id,
            name=form.goalName.data,
            target_amount=form.goalAmount.data,
            deadline=form.deadline.data,
            saving_mode=SavingMode[form.savingsMode.data],
            smart_saver_balance=form.currentSavings.data or 0.0,
            last_saved_at=datetime.utcnow(),
        )
        db.session.add(goal)
        db.session.commit()
        flash("Goal set successfully.", "success")
        return redirect(url_for("main.view_goals"))
    return render_template("set_goal.html", form=form)

@main.route("/goal/deposit/<int:goal_id>", methods=["GET", "POST"])
@login_required
def deposit_to_goal(goal_id):
    goal = FinancialGoal.query.get_or_404(goal_id)
    if goal.user_id != current_user.id:
        flash("Unauthorized access.", "danger")
        return redirect(url_for("main.view_goals"))

    if request.method == "POST":
        try:
            amount = float(request.form.get("amount") or 0)
        except ValueError:
            flash("Invalid input. Enter a numeric value.", "warning")
            return redirect(url_for("main.deposit_to_goal", goal_id=goal.id))

        if amount <= 0:
            flash("Enter a valid amount.", "warning")
            return redirect(url_for("main.deposit_to_goal", goal_id=goal.id))

        account = get_or_create_account(current_user)
        if account.balance < amount:
            flash("Insufficient balance.", "danger")
            return redirect(url_for("main.deposit_to_goal", goal_id=goal.id))

        goal.smart_saver_balance += amount
        account.balance -= amount
        process_transaction(current_user, "Smart Saver Deposit", amount, description=f"Deposited to goal '{goal.name}'")
        flash(f"₹{amount} deposited to your goal.", "success")
        return redirect(url_for("main.view_goals"))

    return render_template("deposit_goal.html", goal=goal)

@main.route("/smart_saver/withdraw/<int:goal_id>", methods=["POST"])
@login_required
def withdraw_from_smart_saver(goal_id):
    goal = FinancialGoal.query.get_or_404(goal_id)
    if goal.user_id != current_user.id:
        flash("Unauthorized", "danger")
        return redirect(url_for("main.view_goals"))

    if goal.smart_saver_balance <= 0:
        flash("Nothing to withdraw.", "warning")
        return redirect(url_for("main.view_goals"))

    account = get_or_create_account(current_user)
    amount = round(goal.smart_saver_balance, 2)
    account.balance += amount
    goal.smart_saver_balance = 0.0
    process_transaction(current_user, "Smart Saver Withdrawal", amount, description=f"Withdrawn from goal '{goal.name}'")
    flash(f"₹{amount} withdrawn from Smart Saver.", "success")
    return redirect(url_for("main.view_goals"))
