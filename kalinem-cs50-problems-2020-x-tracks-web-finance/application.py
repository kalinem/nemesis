import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

from datetime import datetime, timezone
from credit import checksum

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Greeting
    user_id = session["user_id"]
    username = db.execute("SELECT * FROM users WHERE id = ?", user_id)[0]["username"].capitalize()
    message = [f"Welcome back {username}!", "Here are the shares that you currently own:"]

    # Get all the shares the user has where the shares is at least 1
    db_rows = db.execute("SELECT symbol, shares FROM owned WHERE user_id = ? AND shares > 0 ORDER BY symbol", user_id)

    # Organize the data into a list to be presented to the user
    grand_total = 0
    show_rows = []
    for row in db_rows:
        info = lookup(row["symbol"])
        # Copy the symbol and shares from row into data
        data = row
        # Add other data into data
        data["name"] = info["name"]
        price = info["price"]
        total = price * data["shares"]
        data["price"] = usd(price)
        data["total"] = usd(total)
        grand_total += total

        # Add this data dict into the show_rows list
        show_rows.append(data)

    cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]
    grand_total += cash

    return render_template("index.html", message=message, rows=show_rows, cash=usd(cash), total=usd(grand_total))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":

        info = lookup(request.form.get("symbol"))

        # If a symbol is missing
        if not request.form.get("symbol"):
            return apology("missing symbol", 400)

        # If a symbol is not found
        if info is None:
            return apology("invalid symbol", 400)

        # If shares is missing
        if not request.form.get("shares"):
            return apology("missing shares", 400)

        # Variables for later use
        user_id = session["user_id"]
        symbol = info["symbol"]
        price = info["price"]
        shares = int(request.form.get("shares"))
        total = shares * float(price)
        balance = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]

        # If there's not enough money
        if total > balance:
            return apology("not enough money", 400)

        # Else we make and record the transaction and update our data
        balance = balance - total   # new balance
        db.execute("INSERT INTO transactions (user_id, symbol, price, shares, time) VALUES(?, ?, ?, ?, ?)", user_id, symbol, price, shares, datetime.now(timezone.utc))

        # Updates acct. balance
        db.execute("UPDATE users SET cash = ? WHERE id = ?", balance, user_id)

        # Updates shares in owned table
        owned = db.execute("SELECT * FROM owned WHERE user_id = ? AND symbol = ?", user_id, symbol)
        if len(owned) == 0: # i.e. if it doesn't exist yet
            db.execute("INSERT INTO owned VALUES(?, ?, ?)", user_id, symbol, shares)
        else:   # it already exists
            new_shares = owned[0]["shares"] + shares
            db.execute("UPDATE owned SET shares = ? WHERE user_id = ? AND symbol = ?", new_shares, user_id, symbol)

        messages = [f"You have successfully bought {shares} share(s) of {symbol} for {usd(total)}!", f"You have {usd(balance)} left in your bank account."]
        title = "Buy 💸"
        return render_template("success.html", title=title, messages=messages)

    else:
        return render_template("buy.html")

@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    """Allow users to deposit money into their account"""

    user_id = session["user_id"]
    # If method is POST
    if request.method == 'POST':

        # Variables to be used
        title ="Deposit 💳"
        card = request.form.get("card")
        amount = request.form.get("amount")
        errors = []

        # Error handling
        if not card:
            errors.append("error1.html")
        if not amount:
            errors.append("Must enter an amount.")
        else:
            try:
                amount = float(amount)
            except:
                errors.append("Amount must be a number.")

        if len(errors) > 0:
            return render_error(errors, title)

        # Checking the card
        card_info = checksum(card)
        if card_info[0] == 1:
            errors.append("error2.html")
        elif card_info[0] == 2:
            errors.append("error3.html")

        if len(errors) > 0:
            return render_error(errors, title)

        # "Real world" constraints
        amount = float(amount)
        if amount < 20:
            errors.append("Amount must be greater than $20.00.")
        elif amount > 1000:
            errors.append("Your account is limited to depositing $1,000.00 per deposit.")

        if len(errors) > 0:
            return render_error(errors, title)

        # Checks how many deposits were made in the last 5 hours, and 24 hours
        hour = db.execute("SELECT * FROM transactions WHERE ((julianday(CURRENT_TIMESTAMP) - julianday(time)) * 24) < 1 AND symbol = 'CASH' AND user_id = ?", user_id)
        day = db.execute("SELECT * FROM transactions WHERE (julianday(CURRENT_TIMESTAMP) - julianday(time)) < 1 AND symbol = 'CASH' AND user_id = ?", user_id)
        if len(hour) > 0:
            errors.append("You can only make one (1) deposit every hour.")
        elif len(day) > 4:
            errors.append("You can only make five (5) deposits every 24 hours.")

        if len(errors) > 0:
            return render_error(errors, title)

        # Else it's actually good
        elif card_info[0] == 0:
            # Record transactions and update account
            db.execute("INSERT INTO transactions (user_id, symbol, price, time) VALUES(?, ?, ?, ?)", user_id, "CASH", amount, datetime.now(timezone.utc))
            balance = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]
            balance = balance + amount
            db.execute("UPDATE users SET cash = ? WHERE id = ?", balance, user_id)

            # Return success message
            messages = [
                f"You have successfully deposited {usd(amount)} into your account!",
                f"You now have {usd(balance)} in total in your bank account."
                ]
            return render_template("success.html", messages=messages, title="Deposit 💳")

    else:
        return render_template("deposit.html")

# Returns custom error page
def render_error(errors, title):
    return render_template("apology1.html", errors=errors, title=title)

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Get data of all transactions for the current user
    db_rows = db.execute("SELECT * FROM transactions WHERE user_id = ?", session["user_id"])
    for row in db_rows:
        row["price"] = usd(row["price"]) # Formatting

    # Retrurn the webpage
    message = ["Transaction History"]
    return render_template("history.html", rows=db_rows, message=message)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # If method is GET
    if request.method == "GET":
        return render_template("quote.html")

    # Else it is POST and they submitted something
    else:
        info = lookup(request.form.get("symbol"))

        # If a symbol is missing
        if not request.form.get("symbol"):
            return apology("missing symbol", 400)

        # If a symbol is not found
        if info is None:
            return apology("invalid symbol", 400)

        return render_template("quoted.html", info=info, price=usd(info['price']))


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # If the user got here by submitting something for instance
    if request.method == "POST":

        # Show error message if either username or password field is blank
        if not request.form.get("username") or not request.form.get("password"):
            return apology("must provide username and password", 403)

        # Show an error if passwords do not match
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords don't match", 400)

        # Otherwise there are no problems and we store this in out db
        username = request.form.get("username")
        password = request.form.get("password")
        db.execute("INSERT into users (username, hash) VALUES(?, ?)", username, generate_password_hash(password))

        return redirect("/")

    # User reached route via GET
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    user_id = session["user_id"]
    # If method is POST
    if request.method == "POST":

        # If no symbol was selected
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("missing symbol")

        # If symbol is not owned

        owned = db.execute("SELECT shares FROM owned WHERE user_id = ? AND symbol = ?", user_id, symbol)[0]["shares"]
        if owned < 1:
            return apology("share not owned")

        # If no shares are selected
        selected = request.form.get("shares")
        if not selected:
            return apology("missing shares")

        # If 0 shares are selected
        selected = int(selected)
        if selected == 0:
            return apology("shares must be positive")

        # If more than what is owned is selected
        if selected > owned:
            return apology("too many shares")

        # Otherwise, it's all good and we make the transaction
        info = lookup(symbol)
        name = info["name"]
        price = info["price"]
        balance = db.execute("SELECT * FROM users WHERE id = ?", user_id)[0]["cash"] # current money
        balance = balance + (selected * price) # money after sell

        # Record transaction, update acct. balance, and update owned shares
        db.execute("INSERT INTO transactions (user_id, symbol, price, shares, time) VALUES(?, ?, ?, ?, ?)", user_id, symbol, price, (-selected), datetime.now(timezone.utc))
        db.execute("UPDATE users SET cash = ? WHERE id = ?", balance, user_id)
        db.execute("UPDATE owned SET shares = ? WHERE user_id = ? AND symbol = ?", (owned - selected), user_id, symbol)

        # Success message
        title = "Sell 💲"
        messages = [f"You have successfully sold {selected} shares of {name} ({symbol}) for {usd(price * selected)}!",
                f"You now have {usd(balance)} cash in your bank account. 💸💸💸"]
        return render_template("success.html", title=title, messages=messages)

    # Else the method is GET and we display available options
    else:
        # Select all stocks owned
        db_rows = db.execute("SELECT * FROM owned WHERE user_id = ? AND shares > 0 ORDER BY symbol", user_id) # I keep doing this

        return render_template("sell.html", rows=db_rows)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
