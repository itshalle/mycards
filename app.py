from flask import Flask, render_template, request, redirect, url_for, session, Response, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import markdown
import yaml
import os
import re
from uuid import uuid4
from xml.sax.saxutils import escape

app = Flask(__name__)
app.secret_key = 'onlycards2024'

ADMIN_USERNAME = 'itshalle'
ADMIN_PASSWORD = '121299'

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///onlycards.db'
db = SQLAlchemy(app)

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'products')
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
SITE_URL = os.environ.get('SITE_URL', 'https://onlycards.ir').rstrip('/')
BLOG_CONTENT_DIR = os.path.join(app.root_path, 'content', 'blog')

BLOG_CATEGORIES = {
    'emotions-self-awareness': {
        'name': 'احساسات و خودشناسی',
        'intro': 'مقاله‌هایی برای شناخت دقیق‌تر احساسات، پیدا کردن واژه‌های مناسب برای حال درونی و فرق‌گذاشتن میان تجربه‌هایی مثل ترس، اضطراب و نگرانی.',
        'meta_title': 'احساسات و خودشناسی | راهنمای شناخت احساسات | Only Cards',
        'meta_description': 'مقاله‌های کاربردی درباره شناخت احساسات، چرخ احساسات، خودشناسی و تفاوت ترس، اضطراب و نگرانی در زندگی روزمره.'
    },
    'calm-mindfulness': {
        'name': 'آرامش و ذهن‌آگاهی',
        'intro': 'تمرین‌ها و توضیح‌های روشن درباره آرام‌کردن ذهن، ذهن‌آگاهی و مهارت‌های DBT؛ برای استفاده در روزهای شلوغ و موقعیت‌های واقعی.',
        'meta_title': 'آرامش و ذهن‌آگاهی | تمرین‌ها و مهارت‌های DBT | Only Cards',
        'meta_description': 'تمرین‌های کوتاه آرامش، ذهن‌آگاهی و مهارت‌های DBT برای مکث، توجه به لحظه و استفاده در موقعیت‌های واقعی روزمره.'
    },
    'relationships-conversation': {
        'name': 'رابطه و گفت‌وگو',
        'intro': 'مقاله‌هایی درباره سؤال‌پرسیدن، شنیدن بدون قضاوت و ساختن گفت‌وگویی نزدیک‌تر در رابطه؛ بدون تبدیل گفت‌وگو به بازجویی یا تمرینی مصنوعی.',
        'meta_title': 'رابطه و گفت‌وگو | سؤال‌ها و مهارت‌های ارتباطی | Only Cards',
        'meta_description': 'راهنمای گفت‌وگوی عمیق، سؤال برای شناخت پارتنر، گوش‌دادن بدون قضاوت و ساختن ارتباطی نزدیک‌تر و امن‌تر.'
    },
    'quality-time-gifts': {
        'name': 'زمان دو نفره و هدیه',
        'intro': 'ایده‌هایی برای ساختن زمان مشترک، فعالیت‌های دونفره بدون موبایل و انتخاب هدیه‌های شخصی‌تر؛ از قرار در خانه تا هدیه‌ای که واقعاً به علایق طرف مقابل توجه دارد.',
        'meta_title': 'زمان دو نفره و هدیه | ایده برای زوج‌ها | Only Cards',
        'meta_description': 'ایده‌های زمان دونفره، دیت در خانه، سرگرمی بدون موبایل و انتخاب هدیه‌ای شخصی‌تر و معنادار برای آدم‌های مهم زندگی.'
    },
}

BLOG_CATEGORY_BY_NAME = {
    category['name']: slug
    for slug, category in BLOG_CATEGORIES.items()
}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(BLOG_CONTENT_DIR, exist_ok=True)


def load_blog_post(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        source = file.read()

    match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', source, re.DOTALL)
    if not match:
        return None

    metadata = yaml.safe_load(match.group(1)) or {}
    body = match.group(2).strip()

    required_fields = ['title', 'slug', 'description', 'published_at']
    if any(not metadata.get(field) for field in required_fields):
        return None

    metadata['slug'] = str(metadata['slug']).strip().strip('/')
    metadata['published_at'] = str(metadata['published_at'])
    metadata['updated_at'] = str(metadata.get('updated_at') or metadata['published_at'])
    metadata['category'] = metadata.get('category', 'بلاگ Only Cards')
    metadata['category_slug'] = BLOG_CATEGORY_BY_NAME.get(metadata['category'])
    metadata['image'] = str(metadata.get('image') or '').strip().lstrip('/')
    metadata['image_alt'] = metadata.get('image_alt') or metadata['title']
    metadata['draft'] = bool(metadata.get('draft', False))
    metadata['body_markdown'] = body
    metadata['body_html'] = markdown.markdown(
        body,
        extensions=['extra', 'sane_lists']
    )
    return metadata


def get_blog_posts(include_drafts=False):
    posts = []

    if not os.path.isdir(BLOG_CONTENT_DIR):
        return posts

    for filename in os.listdir(BLOG_CONTENT_DIR):
        if not filename.endswith('.md'):
            continue

        post = load_blog_post(os.path.join(BLOG_CONTENT_DIR, filename))
        if not post or (post['draft'] and not include_drafts):
            continue

        posts.append(post)

    posts.sort(key=lambda post: post['slug'])
    posts.sort(key=lambda post: post['published_at'], reverse=True)
    return posts


def get_blog_post(slug):
    for post in get_blog_posts():
        if post['slug'] == slug:
            return post
    return None


def get_blog_category_url(category_name):
    category_slug = BLOG_CATEGORY_BY_NAME.get(category_name)
    if not category_slug:
        return url_for('blog')
    return url_for('blog_category', category_slug=category_slug)


def get_blog_category_cards(posts):
    cards = []
    for category_slug, category in BLOG_CATEGORIES.items():
        card = dict(category)
        card['slug'] = category_slug
        card['count'] = sum(
            1 for post in posts
            if post.get('category_slug') == category_slug
        )
        cards.append(card)
    return cards


@app.after_request
def add_seo_and_cache_headers(response):
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'

    if request.path.startswith('/admin'):
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    elif request.path in ['/cart', '/checkout', '/confirmation']:
        response.headers['X-Robots-Tag'] = 'noindex, follow'

    return response


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


def make_legacy_product_slug(product):
    name = (product.name or '').strip().lower()
    slug = re.sub(r'[^\w\u0600-\u06FF]+', '-', name, flags=re.UNICODE).strip('-')
    return slug or str(product.id)


def make_product_slug(product):
    product_slugs = {
        1: 'calm-cards',
        2: 'couples-conversation-cards',
        3: 'mindfulness-skills-cards',
    }
    return product_slugs.get(product.id, make_legacy_product_slug(product))


def get_product_url(product):
    return url_for('product_by_slug', slug=make_product_slug(product))


def get_product_by_slug(slug):
    for product in Product.query.all():
        if slug in (make_product_slug(product), make_legacy_product_slug(product)):
            return product

    return None


def absolute_url(path):
    if not path.startswith('/'):
        path = '/' + path

    return f"{SITE_URL}{path}"


def absolute_static_url(filename):
    return absolute_url(url_for('static', filename=filename))


def product_image_url(product):
    preview_image = get_product_preview_image(product)

    if not preview_image:
        return ''

    filename = preview_image if '/' in preview_image else f"images/{preview_image}"
    return absolute_static_url(filename)


def clean_meta_description(text, fallback=''):
    text = (text or fallback or '').strip()
    text = re.sub(r'\s+', ' ', text)
    return text[:155]


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
    organization_schema = {
        '@context': 'https://schema.org',
        '@type': 'Organization',
        'name': 'Only Cards',
        'url': SITE_URL,
        'logo': absolute_static_url('favicon_io/apple-touch-icon.png'),
        'sameAs': [
            'https://t.me/onlycards724'
        ],
        'description': 'Only Cards برند کارت‌های فارسی برای آرامش، رابطه، گفت‌وگو، تأمل و mindful play است.'
    }

    website_schema = {
        '@context': 'https://schema.org',
        '@type': 'WebSite',
        'name': 'Only Cards',
        'url': SITE_URL,
        'inLanguage': 'fa-IR',
        'description': 'کارت‌های فارسی برای آرامش، رابطه، گفت‌وگو، تأمل و mindful play.'
    }

    return dict(
        split_product_images=split_product_images,
        get_product_preview_image=get_product_preview_image,
        get_product_url=get_product_url,
        product_image_url=product_image_url,
        organization_schema=organization_schema,
        website_schema=website_schema,
        get_blog_category_url=get_blog_category_url
    )


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    short_description = db.Column(db.String(300), nullable=False, default='')
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
    posts = get_blog_posts()[:3]
    return render_template(
        'index.html',
        products=products,
        posts=posts,
        meta_title='خرید کارت‌های گفت‌وگو و خودشناسی فارسی | Only Cards',
        meta_description='خرید کارت‌های فارسی Only Cards برای آرامش، خودشناسی، گفت‌وگوی عمیق، رابطه عاطفی و وقت‌گذرانی دونفره معنادار بدون موبایل.',
        canonical_url=absolute_url(url_for('index'))
    )


@app.route('/about')
def about():
    return render_template(
        'about.html',
        meta_title='درباره ما | Only Cards',
        meta_description='درباره Only Cards؛ برند فارسی کارت‌هایی برای آرامش، تأمل، رابطه، گفت‌وگو و مراقبت روزمره از خود.',
        canonical_url=absolute_url(url_for('about'))
    )


@app.route('/shipping')
def shipping():
    return render_template(
        'shipping.html',
        meta_title='ارسال و تحویل | Only Cards',
        meta_description='اطلاعات ارسال و تحویل سفارش‌های Only Cards، زمان آماده‌سازی، هزینه ارسال، تأیید پرداخت و بسته‌بندی هدیه.',
        canonical_url=absolute_url(url_for('shipping'))
    )


@app.route('/faq')
def faq():
    return render_template(
        'faq.html',
        meta_title='سوالات پرتکرار | Only Cards',
        meta_description='پاسخ به سوالات پرتکرار درباره خرید، پرداخت، ارسال، بسته‌بندی هدیه و کاربرد کارت‌های Only Cards.',
        canonical_url=absolute_url(url_for('faq'))
    )


@app.route('/shop')
def shop():
    products = Product.query.all()
    return render_template(
        'shop.html',
        products=products,
        meta_title='خرید آنلاین کارت گفت‌وگو و خودشناسی | Only Cards',
        meta_description='خرید آنلاین کارت گفت‌وگو و خودشناسی فارسی برای زوج‌ها، آرامش ذهن، ذهن‌آگاهی، دیت نایت و هدیه‌ای کوچک اما معنادار.',
        canonical_url=absolute_url(url_for('shop'))
    )


@app.route('/blog')
def blog():
    all_posts = get_blog_posts()
    latest_posts = all_posts[:4]
    latest_slugs = {post['slug'] for post in latest_posts}
    remaining_posts = [
        post for post in all_posts
        if post['slug'] not in latest_slugs
    ]

    return render_template(
        'blog.html',
        latest_posts=latest_posts,
        posts=remaining_posts,
        categories=get_blog_category_cards(all_posts),
        meta_title='راهنمای آرامش، خودشناسی و گفت‌وگوی عمیق | Only Cards',
        meta_description='مقاله‌های کاربردی Only Cards درباره شناخت احساسات، ذهن‌آگاهی، رابطه و زمان دو نفره؛ با توضیح‌های روشن و تمرین‌های قابل استفاده.',
        canonical_url=absolute_url(url_for('blog'))
    )



@app.route('/blog/category/<category_slug>')
def blog_category(category_slug):
    category_data = BLOG_CATEGORIES.get(category_slug)
    if not category_data:
        abort(404)

    all_posts = get_blog_posts()
    posts = [
        post for post in all_posts
        if post.get('category_slug') == category_slug
    ]
    category = dict(category_data)
    category['slug'] = category_slug

    category_url = absolute_url(
        url_for('blog_category', category_slug=category_slug)
    )
    blog_url = absolute_url(url_for('blog'))
    item_list_id = f"{category_url}#articles"

    category_schema = {
        '@context': 'https://schema.org',
        '@graph': [
            {
                '@type': 'CollectionPage',
                '@id': category_url,
                'url': category_url,
                'name': category['name'],
                'description': category['meta_description'],
                'inLanguage': 'fa-IR',
                'isPartOf': {
                    '@type': 'Blog',
                    '@id': blog_url,
                    'name': 'بلاگ Only Cards'
                },
                'mainEntity': {'@id': item_list_id}
            },
            {
                '@type': 'ItemList',
                '@id': item_list_id,
                'numberOfItems': len(posts),
                'itemListElement': [
                    {
                        '@type': 'ListItem',
                        'position': position,
                        'name': post['title'],
                        'url': absolute_url(
                            url_for('blog_post', slug=post['slug'])
                        )
                    }
                    for position, post in enumerate(posts, start=1)
                ]
            },
            {
                '@type': 'BreadcrumbList',
                'itemListElement': [
                    {
                        '@type': 'ListItem',
                        'position': 1,
                        'name': 'خانه',
                        'item': absolute_url(url_for('index'))
                    },
                    {
                        '@type': 'ListItem',
                        'position': 2,
                        'name': 'بلاگ',
                        'item': blog_url
                    },
                    {
                        '@type': 'ListItem',
                        'position': 3,
                        'name': category['name'],
                        'item': category_url
                    }
                ]
            }
        ]
    }

    category_cards = get_blog_category_cards(all_posts)
    other_categories = [
        item for item in category_cards
        if item['slug'] != category_slug
    ]

    return render_template(
        'blog_category.html',
        category=category,
        posts=posts,
        other_categories=other_categories,
        category_schema=category_schema,
        meta_title=category['meta_title'],
        meta_description=category['meta_description'],
        canonical_url=category_url
    )


@app.route('/blog/<slug>')
def blog_post(slug):
    post = get_blog_post(slug)
    if not post:
        abort(404)

    canonical_url = absolute_url(url_for('blog_post', slug=post['slug']))
    image_url = absolute_static_url(post['image']) if post['image'] else None
    category_path = get_blog_category_url(post['category'])
    category_page_url = absolute_url(category_path)

    article_schema = {
        '@context': 'https://schema.org',
        '@type': 'Article',
        'headline': post['title'],
        'description': post['description'],
        'datePublished': post['published_at'],
        'dateModified': post['updated_at'],
        'mainEntityOfPage': canonical_url,
        'articleSection': post['category'],
        'isPartOf': {
            '@type': 'CollectionPage',
            '@id': category_page_url,
            'name': post['category']
        },
        'publisher': {
            '@type': 'Organization',
            'name': 'Only Cards',
            'logo': {
                '@type': 'ImageObject',
                'url': absolute_static_url('favicon_io/apple-touch-icon.png')
            }
        }
    }

    if image_url:
        article_schema['image'] = [image_url]

    breadcrumb_schema = {
        '@context': 'https://schema.org',
        '@type': 'BreadcrumbList',
        'itemListElement': [
            {
                '@type': 'ListItem',
                'position': 1,
                'name': 'خانه',
                'item': absolute_url(url_for('index'))
            },
            {
                '@type': 'ListItem',
                'position': 2,
                'name': 'بلاگ',
                'item': absolute_url(url_for('blog'))
            },
            {
                '@type': 'ListItem',
                'position': 3,
                'name': post['category'],
                'item': category_page_url
            },
            {
                '@type': 'ListItem',
                'position': 4,
                'name': post['title'],
                'item': canonical_url
            }
        ]
    }

    return render_template(
        'blog_post.html',
        post=post,
        article_schema=article_schema,
        breadcrumb_schema=breadcrumb_schema,
        category_path=category_path,
        meta_title=f"{post['title']} | Only Cards",
        meta_description=clean_meta_description(post['description']),
        canonical_url=canonical_url,
        og_type='article',
        og_image=image_url
    )


def get_product_seo_metadata(product, fallback_description):
    product_seo = {
        1: (
            'خرید کارت‌های آرامش ذهن | Only Cards',
            'خرید کارت‌های آرامش ذهن با ۵۳ تمرین کوتاه فارسی برای آرامش روزانه، ذهن‌آگاهی، خودمراقبتی و مکث در روزهای پراسترس.'
        ),
        2: (
            'خرید کارت سؤال برای زوج‌ها | کارت‌های ما',
            'خرید کارت سؤال برای زوج‌ها؛ مجموعه‌ای فارسی از سؤال‌ها و فعالیت‌های دونفره برای شناخت بیشتر پارتنر، گفت‌وگوی عمیق و صمیمیت.'
        ),
        3: (
            'خرید کارت تمرین ذهن‌آگاهی فارسی | Only Cards',
            'خرید کارت تمرین ذهن‌آگاهی فارسی با مهارت‌های اصلی DBT برای مشاهده، توصیف، حضور در لحظه و استفاده در موقعیت‌های واقعی روزمره.'
        ),
    }
    return product_seo.get(
        product.id,
        (f'{product.name} | Only Cards', fallback_description)
    )


def get_product_page_content(product):
    product_content = {
        1: {
            'eyebrow': '۵۳ کارت برای مکث‌های کوچک روزانه',
            'section_title': 'برای وقت‌هایی که ذهنت کمی جا می‌خواهد',
            'section_text': 'لازم نیست همیشه برنامه مفصلی برای آرام‌شدن داشته باشی. گاهی یک تمرین کوتاه، چند نفس آگاهانه یا چند دقیقه توجه به حال همین لحظه کافی است تا روزت را با فاصله و آرامش بیشتری ادامه بدهی.',
            'inside_box': [
                '۵۳ کارت تمرین کوتاه و قابل استفاده در زندگی روزمره',
                'تمرین‌هایی برای مکث، ذهن‌آگاهی، آرام‌سازی و خودمراقبتی',
                'جعبه‌ای جمع‌وجور برای نگهداری کارت‌ها',
            ],
            'suitable_for': [
                'استراحت کوتاه میان یک روز شلوغ',
                'ساختن یک روتین ساده برای مراقبت از خود',
                'هدیه به کسی که به چند لحظه آرام‌تر نیاز دارد',
            ],
            'faqs': [
                {
                    'question': 'چطور از کارت‌های آرامش استفاده کنم؟',
                    'answer': 'هر وقت به یک مکث کوتاه نیاز داشتی، یک کارت بردار و همان تمرین را با ریتم خودت انجام بده. کارت‌ها ترتیب اجباری ندارند و لازم نیست هر روز تعداد مشخصی از آن‌ها را انجام بدهی.'
                },
                {
                    'question': 'این کارت‌ها برای شروع ذهن‌آگاهی مناسب‌اند؟',
                    'answer': 'بله. تمرین‌ها کوتاه و ساده نوشته شده‌اند و برای استفاده از آن‌ها لازم نیست تجربه قبلی در مدیتیشن یا ذهن‌آگاهی داشته باشی.'
                },
                {
                    'question': 'می‌توانم کارت‌ها را روی میز کارم بگذارم؟',
                    'answer': 'بله. می‌توانی یک کارت را برای همان روز انتخاب کنی و جایی بگذاری که در زمان استراحت یا میان کارها دوباره ببینیش.'
                },
                {
                    'question': 'آیا کارت‌های آرامش جای روان‌درمانی را می‌گیرند؟',
                    'answer': 'خیر. این کارت‌ها ابزارهایی برای آرامش و مراقبت روزمره از خود هستند و جایگزین روان‌درمانی، مشاوره یا کمک تخصصی نیستند.'
                },
            ],
            'related_slugs': ['five-minute-calm', 'understand-your-emotions'],
        },
        2: {
            'eyebrow': 'سؤال‌ها و فعالیت‌هایی برای دو نفر',
            'section_title': 'برای حرف‌هایی که میان شلوغی روز جا می‌مانند',
            'section_text': 'کارت‌های ما بهانه‌ای‌اند برای اینکه کمی آرام‌تر روبه‌روی هم بنشینید، سؤال تازه‌ای بپرسید و از جواب‌هایی بشنوید که شاید در گفت‌وگوهای معمول روزانه پیش نیایند.',
            'inside_box': [
                'مجموعه‌ای از سؤال‌ها و فعالیت‌های دونفره',
                'موضوع‌هایی برای شناخت بیشتر، خاطره، احساس و آینده',
                'پیشنهادهایی برای قرارهای کوچک و وقت‌گذرانی بدون موبایل',
            ],
            'suitable_for': [
                'زوج‌هایی که می‌خواهند گفت‌وگوی نزدیک‌تری داشته باشند',
                'یک شب دونفره آرام در خانه یا بیرون',
                'هدیه برای یک زوج که دوست دارند زمان مشترک متفاوتی بسازند',
            ],
            'faqs': [
                {
                    'question': 'کارت‌های ما را چطور بازی کنیم؟',
                    'answer': 'یک کارت انتخاب کنید و هر دو به آن پاسخ بدهید یا فعالیتش را با هم انجام دهید. قرار نیست همه کارت‌ها را در یک شب تمام کنید؛ هر بار چند کارت که با حال‌وهوایتان هماهنگ است کافی است.'
                },
                {
                    'question': 'این بازی رقابتی است؟',
                    'answer': 'نه. کارت‌های ما برنده و بازنده ندارند. هدفشان ساختن گفت‌وگو، شناخت بیشتر و چند لحظه مشترک است.'
                },
                {
                    'question': 'برای زوج‌هایی که مدت زیادی با هم بوده‌اند هم مناسب است؟',
                    'answer': 'بله. بعضی سؤال‌ها سراغ جزئیات و تجربه‌هایی می‌روند که حتی بعد از مدت‌ها رابطه ممکن است هنوز درباره‌شان حرف نزده باشید.'
                },
                {
                    'question': 'اگر نخواستیم به یک سؤال جواب بدهیم چه؟',
                    'answer': 'می‌توانید از هر کارتی که در آن لحظه راحت نیستید بگذرید. گفت‌وگوی صمیمی با احساس امنیت و احترام به مرزهای هر دو نفر شکل می‌گیرد.'
                },
            ],
            'related_slugs': ['questions-to-know-your-partner', 'deep-conversation-with-partner'],
        },
        3: {
            'eyebrow': 'تمرین مهارت‌های اصلی ذهن‌آگاهی DBT',
            'section_title': 'یک مهارت کوچک برای همان لحظه‌ای که در آنی',
            'section_text': 'هر کارت بخشی از یک مهارت واقعی ذهن‌آگاهی را به زبان ساده و انسانی همراهت می‌کند؛ برای دیدن فکرها و احساس‌ها، توصیف تجربه و برگشتن به کاری که همین حالا در حال انجامش هستی.',
            'inside_box': [
                'کارت‌های تمرین مرحله‌به‌مرحله مهارت‌های ذهن‌آگاهی',
                'تمرین‌های مشاهده، توصیف و حضور کامل در یک کار',
                'نشانه‌های بصری ساده برای شناختن نوع مهارت',
            ],
            'suitable_for': [
                'تمرین روزانه ذهن‌آگاهی با قدم‌های کوتاه',
                'افرادی که متن‌های طولانی و تمرین‌های پیچیده را دوست ندارند',
                'همراه‌داشتن یک یادآوری کاربردی در موقعیت‌های واقعی روزمره',
            ],
            'faqs': [
                {
                    'question': 'DBT چیست و این کارت‌ها از کدام بخش آن استفاده می‌کنند؟',
                    'answer': 'DBT یا رفتاردرمانی دیالکتیکی مجموعه‌ای از مهارت‌ها دارد. این دک روی مهارت‌های اصلی ذهن‌آگاهی تمرکز می‌کند و تمرین‌های واقعی این بخش را به قدم‌های کوتاه‌تر تبدیل می‌کند.'
                },
                {
                    'question': 'لازم است کارت‌ها را به ترتیب انجام بدهم؟',
                    'answer': 'هر تمرین مسیر مشخص خودش را دارد، اما لازم نیست برای تمام‌کردنش عجله کنی. می‌توانی یک مرحله را بارها در موقعیت‌های مختلف زندگی تمرین کنی و بعد سراغ مرحله بعد بروی.'
                },
                {
                    'question': 'برای استفاده از کارت‌ها باید DBT بلد باشم؟',
                    'answer': 'نه. متن کارت‌ها برای استفاده روزمره نوشته شده است. اگر دوست داشته باشی بیشتر درباره زمینه این مهارت‌ها بدانی، مقاله‌های مرتبط بلاگ هم کنارت هستند.'
                },
                {
                    'question': 'آیا این کارت‌ها ابزار درمانی‌اند؟',
                    'answer': 'خیر. کارت‌ها برای تمرین و یادآوری مهارت‌های روزمره طراحی شده‌اند و جایگزین روان‌درمانی، تشخیص یا توصیه تخصصی نیستند.'
                },
            ],
            'related_slugs': ['what-is-dbt', 'dbt-mindfulness'],
        },
    }

    content = product_content.get(product.id)
    if not content:
        return None

    content = dict(content)
    content['related_posts'] = [
        post for slug in content.pop('related_slugs')
        if (post := get_blog_post(slug))
    ]
    return content


def render_product_detail(product):
    product_description = clean_meta_description(
        product.short_description or product.description,
        fallback='مشاهده و خرید محصول از فروشگاه Only Cards.'
    )
    seo_title, seo_description = get_product_seo_metadata(product, product_description)

    return render_template(
        'product.html',
        product=product,
        page_content=get_product_page_content(product),
        meta_title=seo_title,
        meta_description=seo_description,
        canonical_url=absolute_url(get_product_url(product)),
        og_type='product',
        og_image=product_image_url(product)
    )


@app.route('/products/<slug>')
def product_by_slug(slug):
    product = get_product_by_slug(slug)

    if not product:
        return redirect(url_for('shop'), code=302)

    expected_slug = make_product_slug(product)

    if slug != expected_slug:
        return redirect(get_product_url(product), code=301)

    return render_product_detail(product)


@app.route('/product/<int:id>')
@app.route('/product/<int:id>/<slug>')
def product_legacy_redirect(id, slug=None):
    product = Product.query.get_or_404(id)
    return redirect(get_product_url(product), code=301)


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

    return render_template(
        'cart.html',
        products=products,
        total=total,
        meta_title='سبد خرید | Only Cards',
        meta_description='سبد خرید شما در فروشگاه Only Cards.',
        meta_robots='noindex, follow',
        canonical_url=absolute_url(url_for('cart'))
    )


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

    return render_template(
        'checkout.html',
        meta_title='تکمیل سفارش | Only Cards',
        meta_description='تکمیل سفارش در فروشگاه Only Cards.',
        meta_robots='noindex, follow',
        canonical_url=absolute_url(url_for('checkout'))
    )


@app.route('/confirmation')
def confirmation():
    return render_template(
        'confirmation.html',
        meta_title='ثبت سفارش | Only Cards',
        meta_description='تأیید ثبت سفارش در فروشگاه Only Cards.',
        meta_robots='noindex, follow',
        canonical_url=absolute_url(url_for('confirmation'))
    )


@app.route('/sitemap.xml')
def sitemap():
    pages = [
        {
            'loc': absolute_url(url_for('index')),
            'priority': '1.0',
            'changefreq': 'weekly'
        },
        {
            'loc': absolute_url(url_for('shop')),
            'priority': '0.9',
            'changefreq': 'weekly'
        },
        {
            'loc': absolute_url(url_for('about')),
            'priority': '0.7',
            'changefreq': 'monthly'
        },
        {
            'loc': absolute_url(url_for('shipping')),
            'priority': '0.6',
            'changefreq': 'monthly'
        },
        {
            'loc': absolute_url(url_for('faq')),
            'priority': '0.6',
            'changefreq': 'monthly'
        },
        {
            'loc': absolute_url(url_for('blog')),
            'priority': '0.8',
            'changefreq': 'weekly'
        },
    ]

    blog_posts = get_blog_posts()

    for category_slug, _category in BLOG_CATEGORIES.items():
        category_posts = [
            post for post in blog_posts
            if post.get('category_slug') == category_slug
        ]
        category_page = {
            'loc': absolute_url(
                url_for('blog_category', category_slug=category_slug)
            ),
            'priority': '0.7',
            'changefreq': 'weekly'
        }
        if category_posts:
            category_page['lastmod'] = max(
                post['updated_at'] for post in category_posts
            )
        pages.append(category_page)

    for product in Product.query.all():
        pages.append({
            'loc': absolute_url(get_product_url(product)),
            'priority': '0.8',
            'changefreq': 'weekly'
        })

    for post in blog_posts:
        pages.append({
            'loc': absolute_url(url_for('blog_post', slug=post['slug'])),
            'priority': '0.7',
            'changefreq': 'monthly',
            'lastmod': post['updated_at']
        })

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    ]

    for page in pages:
        page_lines = [
            '  <url>',
            f"    <loc>{escape(page['loc'])}</loc>",
        ]
        if page.get('lastmod'):
            page_lines.append(f"    <lastmod>{escape(page['lastmod'])}</lastmod>")
        page_lines.extend([
            f"    <changefreq>{page['changefreq']}</changefreq>",
            f"    <priority>{page['priority']}</priority>",
            '  </url>'
        ])
        xml_lines.extend(page_lines)

    xml_lines.append('</urlset>')

    return Response('\n'.join(xml_lines), mimetype='application/xml')


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

        return render_template(
            'admin_login.html',
            error=True,
            meta_title='ورود مدیریت | Only Cards',
            meta_description='صفحه ورود مدیریت Only Cards.',
            meta_robots='noindex, nofollow',
            canonical_url=absolute_url(url_for('admin'))
        )

    if not session.get('admin'):
        return render_template(
            'admin_login.html',
            error=False,
            meta_title='ورود مدیریت | Only Cards',
            meta_description='صفحه ورود مدیریت Only Cards.',
            meta_robots='noindex, nofollow',
            canonical_url=absolute_url(url_for('admin'))
        )

    products = Product.query.all()
    orders = Order.query.all()

    return render_template(
        'admin.html',
        products=products,
        orders=orders,
        meta_title='پنل مدیریت | Only Cards',
        meta_description='پنل مدیریت Only Cards.',
        meta_robots='noindex, nofollow',
        canonical_url=absolute_url(url_for('admin'))
    )


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
        short_description=request.form.get('short_description', ''),
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
    product.short_description = request.form.get('short_description', '')
    product.description = request.form['description']
    product.price = float(request.form['price'])
    product.stock = int(request.form['stock'])

    existing_images = split_product_images(product.image)

    remove_indices = request.form.getlist('remove_images')
    remove_indices = [int(index) for index in remove_indices if index.isdigit()]

    preview_index_raw = request.form.get('preview_image_index')
    preview_index = int(preview_index_raw) if preview_index_raw and preview_index_raw.isdigit() else None

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

    all_images = kept_images + new_image_paths

    selected_preview_image = None

    if preview_index is not None and 0 <= preview_index < len(existing_images):
        chosen_image = existing_images[preview_index]

        if chosen_image in all_images:
            selected_preview_image = chosen_image

    if selected_preview_image:
        all_images = [selected_preview_image] + [
            image for image in all_images if image != selected_preview_image
        ]

    product.image = '||'.join(all_images)

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
