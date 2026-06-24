from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import os
from uuid import uuid4

app = Flask(__name__)
app.secret_key = 'onlycards2024'

ADMIN_USERNAME = 'itshalle'
ADMIN_PASSWORD = '121299'

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///onlycards.db'
db = SQLAlchemy(app)

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'products')
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


def allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def save_product_image(file):
    if not file or file.filename == '':
        return None

    if not allowed_image(file.filename):
        raise ValueError('فرمت تصویر باید png، jpg، jpeg، webp یا gif باشد.')

    original_filename = secure_filename(file.filename)
    extension = original_filename.rsplit('.', 1)[1].lower()
    new_filename = f"{uuid4().hex}.{extension}"

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
    file.save(file_path)

    return f"uploads/products/{new_filename}"


def save_product_images(files):
    image_paths = []

    for file in files:
        image_path = save_product_image(file)
        if image_path:
            image_paths.append(image_path)

    return image_paths


def split_product_images(image_text):
    if not image_text:
        return []

    return [image.strip() for image in image_text.split('||') if image.strip()]


def get_product_preview_image(product):
    images = split_product_images(product.image)
    if images:
        return images[0]
    return ''


def delete_product_file(image_path):
    if not image_path:
        return

    if not image_path.startswith('uploads/products/'):
        return

    full_path = os.path.join(app.root_path, 'static', image_path)

    try:
        if os.path.exists(full_path):
            os.remove(full_path)
    except OSError:
        pass


@app.context_processor
def image_helpers():
    return dict(
        split_product_images=split_product_images,
        get_product_preview_image=get_product_preview_image
    )


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False)
    image = db.Column(db.Text, nullable=False, default='')


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(200), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=False)
    customer_address = db.Column(db.Text, nullable=False)
    items = db.Column(db.Text, nullable=False)
    total = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default='pending')


@app.route('/')
def index():
    products = Product.query.all()
    return render_template('index.html', products=products)


@app.route('/shop')
def shop():
    products = Product.query.all()
    return render_template('shop.html', products=products)


@app.route('/product/<int:id>')
def product(id):
    product = Product.query.get_or_404(id)
    return render_template('product.html', product=product)


@app.route('/cart')
def cart():
    cart_items = session.get('cart', [])
    products = []
    total = 0

    for item in cart_items:
        p = Product.query.get(item['id'])
        if p:
            products.append({'product': p, 'quantity': item['quantity']})
            total += p.price * item['quantity']

    return render_template('cart.html', products=products, total=total)


@app.route('/add-to-cart/<int:id>')
def add_to_cart(id):
    cart = session.get('cart', [])

    for item in cart:
        if item['id'] == id:
            item['quantity'] += 1
            session['cart'] = cart
            return redirect(url_for('cart'))

    cart.append({'id': id, 'quantity': 1})
    session['cart'] = cart
    return redirect(url_for('cart'))


@app.route('/remove-from-cart/<int:id>')
def remove_from_cart(id):
    cart = session.get('cart', [])
    cart = [item for item in cart if item['id'] != id]
    session['cart'] = cart
    return redirect(url_for('cart'))


@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if request.method == 'POST':
        cart_items = session.get('cart', [])

        items_text = ', '.join([
            f"Product {item['id']} x{item['quantity']}"
            for item in cart_items
        ])

        total = 0
        for item in cart_items:
            product = Product.query.get(item['id'])
            if product:
                total += product.price * item['quantity']

        order = Order(
            customer_name=request.form['name'],
            customer_phone=request.form['phone'],
            customer_address=request.form['address'],
            items=items_text,
            total=total
        )

        db.session.add(order)
        db.session.commit()

        session['cart'] = []
        return redirect(url_for('confirmation'))

    return render_template('checkout.html')


@app.route('/confirmation')
def confirmation():
    return render_template('confirmation.html')


@app.route('/robots.txt')
def robots():
    return app.send_static_file('robots.txt')


@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin'))

        return render_template('admin_login.html', error=True)

    if not session.get('admin'):
        return render_template('admin_login.html', error=False)

    products = Product.query.all()
    orders = Order.query.all()

    return render_template('admin.html', products=products, orders=orders)


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin'))


@app.route('/admin/add-product', methods=['POST'])
def add_product():
    try:
        image_paths = save_product_images(request.files.getlist('image_file'))
    except ValueError as error:
        return str(error), 400

    product = Product(
        name=request.form['name'],
        description=request.form['description'],
        price=float(request.form['price']),
        stock=int(request.form['stock']),
        image='||'.join(image_paths)
    )

    db.session.add(product)
    db.session.commit()

    return redirect(url_for('admin'))


@app.route('/admin/edit-product/<int:id>', methods=['POST'])
def edit_product(id):
    product = Product.query.get_or_404(id)

    product.name = request.form['name']
    product.description = request.form['description']
    product.price = float(request.form['price'])
    product.stock = int(request.form['stock'])

    existing_images = split_product_images(product.image)

    remove_indices = request.form.getlist('remove_images')
    remove_indices = [int(index) for index in remove_indices if index.isdigit()]

    kept_images = []
    removed_images = []

    for index, image in enumerate(existing_images):
        if index in remove_indices:
            removed_images.append(image)
        else:
            kept_images.append(image)

    for image in removed_images:
        delete_product_file(image)

    try:
        new_image_paths = save_product_images(request.files.getlist('image_file'))
    except ValueError as error:
        return str(error), 400

    product.image = '||'.join(kept_images + new_image_paths)

    db.session.commit()

    return redirect(url_for('admin'))


@app.route('/admin/delete-product/<int:id>')
def delete_product(id):
    product = Product.query.get_or_404(id)

    product_images = split_product_images(product.image)
    for image in product_images:
        delete_product_file(image)

    db.session.delete(product)
    db.session.commit()

    return redirect(url_for('admin'))


@app.route('/admin/update-order/<int:id>', methods=['POST'])
def update_order(id):
    order = Order.query.get_or_404(id)
    order.status = request.form['status']

    db.session.commit()

    return redirect(url_for('admin'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()

        if Product.query.count() == 0:
            sample_products = [
                Product(
                    name='کارت‌های مدیریت استرس',
                    description='مجموعه کارت‌هایی برای مدیریت استرس و اضطراب روزانه',
                    price=150000,
                    stock=100,
                    image='stress.jpg'
                ),
                Product(
                    name='کارت های عشق',
                    description='مجموعه کارت‌هایی برای تقویت روابط عاشقانه',
                    price=150000,
                    stock=100,
                    image='love.jpg'
                ),
                Product(
                    name='کارت های مهارت های DBT',
                    description='مجموعه کارت‌هایی بر اساس مهارت‌های درمان دیالکتیکی رفتاری',
                    price=150000,
                    stock=100,
                    image='dbt.jpg'
                ),
            ]

            db.session.add_all(sample_products)
            db.session.commit()

    app.run(debug=True)