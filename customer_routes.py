from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from .models import User, Account, Transaction, db
import numpy as np
from datetime import datetime

customer_bp = Blueprint("customer_bp", __name__)

def get_or_create_account(user):
    if not user.account:
        account = Account(user_id=user.id, balance=0.0)
        db.session.add(account)
        db.session.commit()
        return account
    return user.account

@customer_bp.route("/dashboard")
@login_required
def dashboard():
    account = get_or_create_account(current_user)
    balance = account.balance
    account_number = account.account_number
    return render_template("dashboard.html", balance=balance, account_number=account_number)


# ---------------- LOGOUT ----------------
@customer_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('customer.login'))


# ---------------- REGISTER ----------------
@customer_bp.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()

    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        full_name = request.form['name']
        place = request.form['place']
        mobile_number = request.form['mobile_number']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        face_data = request.form.get('face_image')

        if password != confirm_password:
            flash("Passwords do not match", "danger")
            return render_template("register.html", form=form)

        if User.query.filter_by(email=email).first():
            flash("Email already registered", "danger")
            return render_template("register.html", form=form)

        user = User(username=username, email=email, name=full_name,
                    place=place, mobile_number=mobile_number)

        if face_data:
            face_data = face_data.split(',')[1]
            try:
                img = Image.open(BytesIO(base64.b64decode(face_data))).convert("RGB")
                np_img = np.array(img)
                user.face_encoding = get_face_encoding(np_img).tobytes()
            except Exception:
                flash("Failed to process face image.", "warning")
                user.face_encoding = None

        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        account_number = "SB" + str(random.randint(10000000, 99999999))
        account = Account(user_id=user.id, account_number=account_number, balance=0.0)
        db.session.add(account)
        db.session.commit()

        flash("Registered successfully! Please login to continue.", "success")
        return redirect(url_for('customer.login'))

    return render_template("register.html", form=form)


# ---------------- EMI CALCULATOR ----------------
@customer_bp.route('/emi_calculator', methods=['GET', 'POST'])
@login_required
def emi_calculator():
    emi = total_payment = total_interest = None
    tenure_display = ""
    principal = request.form.get('principal', '')
    interest_rate = request.form.get('interest_rate', '')
    tenure_value = request.form.get('tenure', '')
    tenure_unit = request.form.get('tenure_unit', 'months')

    if request.method == 'POST':
        try:
            principal = float(principal)
            rate = float(interest_rate)
            tenure = int(tenure_value)
            if principal <= 0 or rate <= 0 or tenure <= 0 or not (1 <= rate <= 30):
                raise ValueError

            tenure_months = tenure * 12 if tenure_unit == 'years' else tenure
            tenure_display = f"{tenure} {'Years' if tenure_unit == 'years' else 'Months'}"

            monthly_rate = rate / 12 / 100
            emi = (principal * monthly_rate * (1 + monthly_rate) ** tenure_months) / (
                (1 + monthly_rate) ** tenure_months - 1)
            total_payment = emi * tenure_months
            total_interest = total_payment - principal

        except Exception:
            flash('Invalid input. Please enter valid numbers.', 'danger')

    return render_template('emi_calculator.html',
                           emi=emi,
                           total_payment=total_payment,
                           total_interest=total_interest,
                           principal=principal,
                           interest_rate=interest_rate,
                           tenure_value=tenure_value,
                           tenure_unit=tenure_unit,
                           tenure_display=tenure_display)


# ---------------- DEPOSIT ----------------
@customer_bp.route('/deposit', methods=['GET', 'POST'])
@login_required
def deposit():
    form = DepositForm()
    if form.validate_on_submit():
        amount = float(form.amount.data)
        account = current_user.account
        if not account:
            flash('No account found.', 'danger')
            return redirect(url_for('customer.dashboard'))

        if amount <= 0:
            flash('Please enter a valid positive amount.', 'danger')
            return render_template('deposit.html', form=form)

        account.balance += amount
        txn = Transaction(type="Deposit", amount=amount, user_id=current_user.id, timestamp=datetime.utcnow())
        db.session.add(txn)
        db.session.commit()
        flash('Deposit successful! Your balance has been updated.', 'success')
        return redirect(url_for('customer.dashboard'))

    return render_template('deposit.html', form=form)


# ---------------- WITHDRAW ----------------
@customer_bp.route('/withdraw', methods=['GET', 'POST'])
@login_required
def withdraw():
    form = WithdrawForm()
    if form.validate_on_submit():
        amount = float(form.amount.data)
        account = current_user.account
        if not account:
            flash("Account not found.", "danger")
            return redirect(url_for('customer.dashboard'))

        if amount <= 0 or amount > account.balance:
            flash("Invalid amount or insufficient funds.", "danger")
            return render_template("withdraw.html", form=form)

        account.balance -= amount
        txn = Transaction(type="Withdraw", amount=amount, user_id=current_user.id, timestamp=datetime.utcnow())
        db.session.add(txn)
        db.session.commit()
        flash("Withdrawal successful!", "success")
        return redirect(url_for('customer.dashboard'))

    return render_template("withdraw.html", form=form)


# ---------------- TRANSFER ----------------
@customer_bp.route('/transfer', methods=['GET', 'POST'])
@login_required
def transfer():
    if request.method == 'POST':
        beneficiary_name = request.form.get('beneficiary_name')
        account_number = request.form.get('account_number')
        amount_str = request.form.get('amount')
        save_contact = request.form.get('save_contact')

        try:
            amount = float(amount_str)
        except ValueError:
            flash("Invalid amount entered.", "danger")
            return redirect(url_for('customer.transfer'))

        sender = current_user.account
        recipient = Account.query.filter_by(account_number=account_number).first()

        if not recipient:
            flash("Recipient not found.", "danger")
        elif recipient.id == sender.id:
            flash("Cannot transfer to your own account.", "warning")
        elif amount <= 0:
            flash("Amount must be greater than 0.", "warning")
        elif sender.balance < amount:
            flash("Insufficient funds.", "danger")
        else:
            sender.balance -= amount
            recipient.balance += amount
            txn_sender = Transaction(user_id=current_user.id, type='Transfer', amount=amount,
                                     recipient_account=account_number, beneficiary_name=beneficiary_name, status="Success")
            db.session.add(txn_sender)
            txn_recipient = Transaction(user_id=recipient.user_id, type='Received', amount=amount,
                                        recipient_account=sender.account_number, beneficiary_name=current_user.name, status="Success")
            db.session.add(txn_recipient)

            if save_contact:
                exists = SavedContact.query.filter_by(user_id=current_user.id, account_number=account_number).first()
                if not exists:
                    new_contact = SavedContact(user_id=current_user.id, name=beneficiary_name, account_number=account_number)
                    db.session.add(new_contact)

            db.session.commit()
            flash("Transfer successful!", "success")
            return redirect(url_for('customer.dashboard'))

    saved_contacts = SavedContact.query.filter_by(user_id=current_user.id).all()
    return render_template("transfer.html", saved_contacts=saved_contacts)


# ---------------- VIEW CONTACTS ----------------
@customer_bp.route('/contacts')
@login_required
def view_contacts():
    contacts = SavedContact.query.filter_by(user_id=current_user.id).all()
    return render_template("contacts.html", contacts=contacts)


# ---------------- DELETE ACCOUNT ----------------
@customer_bp.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    user = current_user
    account = user.account
    if account:
        db.session.delete(account)
    db.session.delete(user)
    db.session.commit()
    logout_user()
    flash("Your account has been deleted.", "success")
    return redirect(url_for('customer.login'))
