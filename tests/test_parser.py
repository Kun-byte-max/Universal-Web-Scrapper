import pytest
from app.scraper.parser import PageParser

HTML_JSON_LD_PRODUCT = """
<!DOCTYPE html>
<html>
<head>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org/",
        "@type": "Product",
        "name": "Wireless Noise-Canceling Headphones",
        "image": [
            "https://example.com/images/hp1.jpg",
            "https://example.com/images/hp2.jpg"
        ],
        "description": "High-fidelity audio with active noise cancellation.",
        "sku": "HP-9000",
        "brand": {
            "@type": "Brand",
            "name": "AudioTech"
        },
        "offers": {
            "@type": "Offer",
            "priceCurrency": "USD",
            "price": "299.99",
            "availability": "https://schema.org/InStock"
        }
    }
    </script>
</head>
<body></body>
</html>
"""

HTML_JSON_LD_GRAPH = """
<!DOCTYPE html>
<html>
<head>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "headline": "Top 10 Web Scraping Tools in 2026",
                "description": "A comprehensive guide to web extraction.",
                "image": "/images/article_banner.png",
                "url": "/blog/top-web-scraping-tools"
            }
        ]
    }
    </script>
</head>
<body></body>
</html>
"""

HTML_OPEN_GRAPH = """
<!DOCTYPE html>
<html>
<head>
    <title>Awesome Gaming Laptop | Shop</title>
    <meta property="og:title" content="Awesome Gaming Laptop" />
    <meta property="og:description" content="NVIDIA RTX 4080 powered gaming laptop." />
    <meta property="og:image" content="https://example.com/laptop.png" />
    <meta property="og:url" content="https://example.com/laptops/gaming-1" />
    <meta property="product:price:amount" content="1499.00" />
    <meta property="product:price:currency" content="USD" />
</head>
<body></body>
</html>
"""

HTML_CARDS = """
<!DOCTYPE html>
<html>
<body>
    <div class="product-catalog">
        <div class="product-card">
            <a href="/products/item-1"><img data-src="/img/item1.jpg" alt="Item One"></a>
            <h3 class="title">Smart Watch Series 5</h3>
            <p class="description">Fitness tracking with OLED screen.</p>
            <span class="price">$199.50</span>
        </div>
        <div class="product-card">
            <a href="/products/item-2"><img srcset="/img/item2_small.jpg 300w, /img/item2_large.jpg 800w" alt="Item Two"></a>
            <h3 class="title">Bluetooth Speaker</h3>
            <p class="description">Waterproof outdoor speaker.</p>
            <span class="price">$49.99</span>
        </div>
    </div>
</body>
</html>
"""

HTML_MALFORMED_JSON_LD = """
<!DOCTYPE html>
<html>
<head>
    <script type="application/ld+json">
    {
        "@type": "Product",
        "name": "Broken JSON Item",
        "price": 50.00,
    }
    </script>
</head>
<body></body>
</html>
"""

def test_json_ld_product_extraction():
    parser = PageParser(HTML_JSON_LD_PRODUCT, "https://example.com/products/hp")
    records, strategy = parser.parse_records()
    
    assert len(records) == 1
    rec = records[0]
    assert rec["title"] == "Wireless Noise-Canceling Headphones"
    assert rec["sku"] == "HP-9000"
    assert rec["brand"] == "AudioTech"
    assert rec["price"] == 299.99
    assert rec["currency"] == "USD"
    assert rec["image_url"] == "https://example.com/images/hp1.jpg"
    assert len(rec["image_urls"]) == 2
    assert "Strategy A" in strategy

def test_json_ld_nested_graph_article():
    parser = PageParser(HTML_JSON_LD_GRAPH, "https://example.com/blog/")
    records, strategy = parser.parse_records()
    
    assert len(records) == 1
    rec = records[0]
    assert rec["title"] == "Top 10 Web Scraping Tools in 2026"
    assert rec["product_url"] == "https://example.com/blog/top-web-scraping-tools"
    assert rec["image_url"] == "https://example.com/images/article_banner.png"

def test_open_graph_extraction():
    parser = PageParser(HTML_OPEN_GRAPH, "https://example.com/laptop")
    records, strategy = parser.parse_records()
    
    assert len(records) == 1
    rec = records[0]
    assert rec["title"] == "Awesome Gaming Laptop"
    assert rec["price"] == 1499.00
    assert rec["currency"] == "USD"

def test_html_product_card_extraction():
    parser = PageParser(HTML_CARDS, "https://example.com/shop")
    records, strategy = parser.parse_records()
    
    assert len(records) == 2
    assert "Strategy B" in strategy
    
    # Check item 1 with lazy data-src & relative URL resolution
    item1 = records[0]
    assert item1["title"] == "Smart Watch Series 5"
    assert item1["product_url"] == "https://example.com/products/item-1"
    assert item1["image_url"] == "https://example.com/img/item1.jpg"
    assert item1["price"] == 199.50
    assert item1["currency"] == "USD"

    # Check item 2 with srcset resolution
    item2 = records[1]
    assert item2["title"] == "Bluetooth Speaker"
    assert item2["image_url"] == "https://example.com/img/item2_large.jpg"

def test_malformed_json_ld_handling():
    parser = PageParser(HTML_MALFORMED_JSON_LD, "https://example.com/broken")
    records, strategy = parser.parse_records()
    # Soft sanitation should clean trailing comma or fall through gracefully without exception
    assert isinstance(records, list)

def test_b2b_priceless_product_extraction():
    html_b2b = """<!DOCTYPE html><html><body><main><h1>Automated Pharmacy Dispensing System</h1><p>We provide Automated pharmacy dispensing system which is a decentralized medication distribution system that provides computer controlled storage.</p><img src="/img/apds.jpg" alt="APDS"></main></body></html>"""
    parser = PageParser(html_b2b, "https://example.com/apds")
    records, strategy = parser.parse_records()
    assert len(records) == 1
    assert records[0]["title"] == "Automated Pharmacy Dispensing System"
    assert records[0]["price"] is None
    assert records[0]["image_url"] == "https://example.com/img/apds.jpg"
    assert "Strategy C" in strategy

def test_generic_contact_page_rejected():
    html_contact = """
    <!DOCTYPE html>
    <html>
    <head><title>Contact – Med freshe Private Limited</title></head>
    <body>
        <main>
            <h1>Contact Us</h1>
            <p>Address : UNG Tower, 3rd Floor, Building No. 2 & 3, Central Market, Punjabi Bagh West, New Delhi-110026, INDIA</p>
            <p>Phone : (+91-11) 4545 9999 (Hunting Lines), (+91-11) 2522 8890 | Fax : (+91-11) 2522 8702</p>
            <p>E-mail : info@example.com, sales@example.com | Website : www.example.com</p>
            <img src="/img/headquarters.jpg" alt="Corporate Office">
        </main>
    </body>
    </html>
    """
    parser = PageParser(html_contact, "https://example.com/contact")
    records, strategy = parser.parse_records()
    assert len(records) == 0

def test_quality_control_compliance_page_rejected():
    html_qc = """
    <!DOCTYPE html>
    <html>
    <head><title>Quality Control – Med freshe Private Limited</title></head>
    <body>
        <main>
            <h1>Quality Control</h1>
            <p>We are in possession of the company quality system on the basis of Directive 93/42/EEC for Medical Devices (MDD), EN ISO 13485 and UNI EN ISO 9001.</p>
            <p>These certifications as well as product certifications for steam sterilization systems ensure high level compliance and patient safety.</p>
            <p>Motivation is one of our core values for superior healthcare quality standards.</p>
            <img src="/img/ce_cert.jpg" alt="CE Mark">
            <img src="/img/iso_cert.jpg" alt="ISO Certification">
        </main>
    </body>
    </html>
    """
    parser = PageParser(html_qc, "https://example.com/quality-control")
    records, strategy = parser.parse_records()
    assert len(records) == 0

def test_generic_homepage_rejected():
    html_home = """
    <!DOCTYPE html>
    <html>
    <head><title>Home – Med freshe Private Limited</title></head>
    <body>
        <main>
            <h1>Welcome to Med Freshe</h1>
            <p>Welcome to our website. We are dedicated to providing quality content, industrial equipment, and engineering services.</p>
            <p>Explore our healthcare technology and facility engineering solutions to learn more about our offerings.</p>
            <p>© Copyright 2025. All Rights Reserved across all regions.</p>
            <img src="/img/company_overview.jpg" alt="Overview">
        </main>
    </body>
    </html>
    """
    parser = PageParser(html_home, "https://example.com/")
    records, strategy = parser.parse_records()
    assert len(records) == 0

def test_unbranded_company_homepage_root_url_rejected():
    html_unbranded_home = """
    <!DOCTYPE html>
    <html>
    <head><title>Med freshe Private Limited – Med Freshe Pvt Ltd</title></head>
    <body>
        <main>
            <h1>Med freshe Private Limited</h1>
            <p>Welcome to our website. We are dedicated to providing quality content and services.</p>
            <p>Explore our site to learn more about what we offer in medical systems and engineering.</p>
            <p>© Copyright 2025. All Rights Reserved.</p>
            <img src="/img/office_building.jpg" alt="Med Freshe HQ">
        </main>
    </body>
    </html>
    """
    parser1 = PageParser(html_unbranded_home, "https://medfreshe.com/")
    records1, strategy1 = parser1.parse_records()
    assert len(records1) == 0

    parser2 = PageParser(html_unbranded_home, "https://medfreshe.com")
    records2, strategy2 = parser2.parse_records()
    assert len(records2) == 0

def test_root_homepage_with_product_json_ld_extracted():
    html_json_ld_home = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Med Freshe Medical Innovations</title>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org/",
            "@type": "Product",
            "name": "Featured Medical Monitor",
            "image": "https://example.com/img/monitor.jpg",
            "description": "Hospital grade patient monitoring station.",
            "sku": "MM-500",
            "offers": {
                "@type": "Offer",
                "price": "1250.00",
                "priceCurrency": "USD",
                "availability": "https://schema.org/InStock"
            }
        }
        </script>
    </head>
    <body>
        <h1>Welcome to Med Freshe</h1>
        <p>Leading provider of medical monitoring devices.</p>
    </body>
    </html>
    """
    parser = PageParser(html_json_ld_home, "https://example.com/")
    records, strategy = parser.parse_records()
    assert len(records) == 1
    assert records[0]["title"] == "Featured Medical Monitor"
    assert records[0]["price"] == 1250.00
    assert "Strategy A" in strategy

def test_root_homepage_with_product_cards_extracted():
    html_cards_home = """
    <!DOCTYPE html>
    <html>
    <head><title>Acme Healthcare Supply</title></head>
    <body>
        <h1>Welcome to Acme Healthcare Supply</h1>
        <p>Browse our featured hospital equipment below.</p>
        <div class="product-catalog">
            <div class="product-card">
                <a href="/products/portable-oxygen"><img src="/img/oxygen.jpg" alt="Oxygen Unit"></a>
                <h3>Portable Oxygen Unit</h3>
                <p>Lightweight medical oxygen cylinder and regulator.</p>
                <span class="price">$450.00</span>
            </div>
            <div class="product-card">
                <a href="/products/iv-stand"><img src="/img/iv.jpg" alt="IV Stand"></a>
                <h3>Stainless Steel IV Stand</h3>
                <p>Mobile 4-hook intravenous pole.</p>
                <span class="price">$120.00</span>
            </div>
        </div>
    </body>
    </html>
    """
    parser = PageParser(html_cards_home, "https://example.com/")
    records, strategy = parser.parse_records()
    assert len(records) == 2
    assert records[0]["title"] == "Portable Oxygen Unit"
    assert records[1]["title"] == "Stainless Steel IV Stand"
    assert "Strategy B" in strategy

def test_valid_equipment_title_containing_generic_term_not_excluded():
    html_thermometer = """
    <!DOCTYPE html>
    <html>
    <head><title>Non-Contact Infrared Thermometer – Medical Devices</title></head>
    <body>
        <main>
            <h1>Non-Contact Infrared Thermometer</h1>
            <p>High-precision non-contact infrared medical thermometer for clinical and hospital triage screening.</p>
            <p>Equipped with instant digital LCD display and fever alarm for pediatric and adult diagnostics.</p>
            <img src="/img/thermometer.jpg" alt="Infrared Thermometer">
        </main>
    </body>
    </html>
    """
    parser = PageParser(html_thermometer, "https://example.com/thermometer")
    records, strategy = parser.parse_records()
    assert len(records) == 1
    assert records[0]["title"] == "Non-Contact Infrared Thermometer"

def test_json_ld_aggregate_offer_extraction():
    html_agg = """<!DOCTYPE html><html><head><script type="application/ld+json">{"@type": "Product", "name": "Bulk Monitor", "offers": {"@type": "AggregateOffer", "lowPrice": "149.99", "highPrice": "199.99", "priceCurrency": "USD"}}</script></head><body></body></html>"""
    parser = PageParser(html_agg, "https://example.com/monitor")
    records, strategy = parser.parse_records()
    assert len(records) == 1
    assert records[0]["title"] == "Bulk Monitor"
    assert records[0]["price"] == 149.99
    assert records[0]["currency"] == "USD"

def test_quotes_site_rejection():
    html_quotes = """<!DOCTYPE html><html><head><title>Quotes to Scrape</title></head><body><main><h1>Quotes to Scrape</h1><p>“The world as we have created it is a process of our thinking. It cannot be changed without changing our thinking.”</p></main></body></html>"""
    parser = PageParser(html_quotes, "https://quotes.toscrape.com/")
    records, strategy = parser.parse_records()
    assert len(records) == 0

def test_image_level_title_and_caption_extraction():
    html_gallery = """
    <!DOCTYPE html>
    <html>
    <body>
        <main>
            <h1>Medical Gas Pipeline System</h1>
            <p>Comprehensive medical gas equipment installation for modern hospitals.</p>
            
            <h2>Intensive Care Unit</h2>
            <figure>
                <img src="/img/icu1.jpg" alt="Vertical Type ICU" title="Vertical Type Intensive Care Units">
                <figcaption>Vertical Type Intensive Care Units Caption</figcaption>
            </figure>
            
            <div class="equipment-card">
                <h3>Bridge Type Intensive Care Units</h3>
                <img src="/img/icu2.jpg" alt="Bridge Type ICU">
            </div>
        </main>
    </body>
    </html>
    """
    parser = PageParser(html_gallery, "https://example.com/gas-pipeline")
    records, strategy = parser.parse_records()
    assert len(records) == 1
    rec = records[0]
    assert len(rec["images"]) == 2
    
    img1 = rec["images"][0]
    assert img1["image_url"] == "https://example.com/img/icu1.jpg"
    assert img1["title"] == "Vertical Type Intensive Care Units Caption"
    assert img1["caption"] == "Vertical Type Intensive Care Units Caption"
    assert img1["section_title"] == "Intensive Care Unit"

    img2 = rec["images"][1]
    assert img2["image_url"] == "https://example.com/img/icu2.jpg"
    assert img2["title"] == "Bridge Type Intensive Care Units"
    assert img2["alt"] == "Bridge Type ICU"
    assert img2["section_title"] == "Intensive Care Unit"

def test_image_visible_label_in_widget_and_h3_section():
    html = """
    <!DOCTYPE html>
    <html>
    <body>
        <main>
            <h1>Medical Gas Pipeline System</h1>
            <p>Industrial medical gas equipment description for healthcare facilities.</p>
            <h3>Intensive Care Unit</h3>
            <div class="panel-grid-cell">
                <div class="widget_sow-editor">
                    <p><strong>Vertical Type Intensive Care Units</strong></p>
                </div>
                <div class="widget_sow-image">
                    <img src="/img/vehical.jpg" alt="" />
                </div>
            </div>
            <div class="panel-grid-cell">
                <div class="widget_sow-editor">
                    <p><strong>Bridge Type Intensive Care Units</strong></p>
                </div>
                <div class="widget_sow-image">
                    <img src="/img/bridge.jpg" alt="" />
                </div>
            </div>
            <div class="panel-grid-cell">
                <div class="widget_sow-image">
                    <img src="/img/unlabeled.jpg" alt="" />
                </div>
            </div>
            <h3>Operating Unit</h3>
            <div class="generic-product-card">
                <h4>Surgical Pendant</h4>
                <img src="/img/pendant.jpg" alt="Surgical Pendant Alt" />
            </div>
        </main>
    </body>
    </html>
    """
    parser = PageParser(html, "https://example.com/system")
    records, strategy = parser.parse_records()
    assert len(records) == 1
    images = records[0]["images"]
    assert len(images) == 4

    # 1. Image with p > strong in preceding sibling widget under h3 section
    assert images[0]["image_url"] == "https://example.com/img/vehical.jpg"
    assert images[0]["title"] == "Vertical Type Intensive Care Units"
    assert images[0]["section_title"] == "Intensive Care Unit"

    # 2. Distinct image with different label under same section (no label leakage)
    assert images[1]["image_url"] == "https://example.com/img/bridge.jpg"
    assert images[1]["title"] == "Bridge Type Intensive Care Units"
    assert images[1]["section_title"] == "Intensive Care Unit"

    # 3. Image with no label does not fabricate title
    assert images[2]["image_url"] == "https://example.com/img/unlabeled.jpg"
    assert images[2]["title"] is None
    assert images[2]["section_title"] == "Intensive Care Unit"

    # 4. Generic product card with h4 card heading under new h3 section
    assert images[3]["image_url"] == "https://example.com/img/pendant.jpg"
    assert images[3]["title"] == "Surgical Pendant"
    assert images[3]["alt"] == "Surgical Pendant Alt"
    assert images[3]["section_title"] == "Operating Unit"


# ==============================================================================
# PHASE 17.14: HTML Card False-Positive Prevention & Evidence Validation
# ==============================================================================

def test_phase17_14_header_box_quotes_to_scrape_rejected():
    """Verify header-box containing 'Quotes to Scrape' is rejected by StrategyHTMLCards."""
    html = """
    <!DOCTYPE html>
    <html>
    <body>
        <div class="row header-box">
            <div class="col-md-8">
                <h1>
                    <a href="/" style="text-decoration: none">Quotes to Scrape</a>
                </h1>
            </div>
            <div class="col-md-4">
                <p>
                    <a href="/login">Login</a>
                </p>
            </div>
        </div>
        <div class="row">
            <div class="col-md-8">
                <div class="quote">
                    <span class="text">“The world as we have created it is a process of our thinking.”</span>
                    <span>by <small class="author">Albert Einstein</small></span>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    parser = PageParser(html, "https://quotes.toscrape.com/")
    records, strategy = parser.parse_records()
    assert len(records) == 0
    assert strategy == "None"


def test_phase17_14_tags_box_top_ten_tags_rejected():
    """Verify tags-box containing 'Top Ten tags' is rejected by StrategyHTMLCards."""
    html = """
    <!DOCTYPE html>
    <html>
    <body>
        <div class="col-md-4 tags-box">
            <h2>Top Ten tags</h2>
            <span class="tag-item">
                <a class="tag" href="/tag/love/" style="font-size: 28px">love</a>
            </span>
            <span class="tag-item">
                <a class="tag" href="/tag/inspirational/" style="font-size: 26px">inspirational</a>
            </span>
        </div>
    </body>
    </html>
    """
    parser = PageParser(html, "https://quotes.toscrape.com/")
    records, strategy = parser.parse_records()
    assert len(records) == 0
    assert strategy == "None"


def test_phase17_14_quotes_homepage_full_layout_rejected():
    """Verify entire quotes homepage layout with both header-box and tags-box yields zero records."""
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head><title>Quotes to Scrape</title></head>
    <body>
        <div class="container">
            <div class="row header-box">
                <div class="col-md-8">
                    <h1><a href="/">Quotes to Scrape</a></h1>
                </div>
                <div class="col-md-4"><p><a href="/login">Login</a></p></div>
            </div>
            <div class="row">
                <div class="col-md-8">
                    <div class="quote">
                        <span class="text">“A day without sunshine is like, you know, night.”</span>
                        <span>by <small>Steve Martin</small></span>
                    </div>
                </div>
                <div class="col-md-4 tags-box">
                    <h2>Top Ten tags</h2>
                    <span class="tag-item"><a class="tag" href="/tag/love/">love</a></span>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    parser = PageParser(html, "https://quotes.toscrape.com/")
    records, strategy = parser.parse_records()
    assert len(records) == 0
    assert strategy == "None"


def test_phase17_14_genuine_product_box_accepted():
    """Verify genuine product cards using class 'product-box' or 'box' are still extracted."""
    html = """
    <!DOCTYPE html>
    <html>
    <body>
        <div class="catalog-container">
            <div class="product-box">
                <a href="/products/junction-box-ip66">
                    <img src="/img/junction_box.jpg" alt="Weatherproof Junction Box" />
                </a>
                <h3>Weatherproof Junction Box IP66</h3>
                <p class="description">Industrial polycarbonate junction box with pre-molded silicone gaskets.</p>
                <span class="price">$24.95</span>
            </div>
            <div class="product-box">
                <a href="/products/terminal-box-pro">
                    <img src="/img/terminal_box.jpg" alt="Modular Terminal Box" />
                </a>
                <h3>Modular Terminal Box Pro</h3>
                <p class="description">Heavy duty terminal enclosure box with DIN rail mounting kit.</p>
                <span class="price">$42.50</span>
            </div>
        </div>
    </body>
    </html>
    """
    parser = PageParser(html, "https://example.com/enclosures")
    records, strategy = parser.parse_records()
    assert len(records) == 2
    assert "Strategy B" in strategy
    assert records[0]["title"] == "Weatherproof Junction Box IP66"
    assert records[0]["price"] == 24.95
    assert records[0]["image_url"] == "https://example.com/img/junction_box.jpg"
    assert records[1]["title"] == "Modular Terminal Box Pro"
    assert records[1]["price"] == 42.50
    assert records[1]["image_url"] == "https://example.com/img/terminal_box.jpg"


def test_phase17_14_incidental_generic_word_in_product_title_accepted():
    """Verify legitimate products containing incidental words like 'contact' or 'company' are retained."""
    html = """
    <!DOCTYPE html>
    <html>
    <body>
        <div class="product-grid">
            <div class="item-card">
                <a href="/products/daily-contact-lenses">
                    <img src="/img/contact_lenses.jpg" alt="Daily Contact Lenses" />
                </a>
                <h3>Daily Contact Lenses 90-Pack</h3>
                <p class="description">Hydrating daily disposable contact lenses with UV protection.</p>
                <span class="price">$65.00</span>
            </div>
            <div class="item-card">
                <a href="/products/company-oxygen-regulator">
                    <img src="/img/regulator.jpg" alt="Company Oxygen Regulator" />
                </a>
                <h3>Company Brand Oxygen Regulator</h3>
                <p class="description">Medical gas cylinder pressure regulator with calibrated flow gauge.</p>
                <span class="price">$110.00</span>
            </div>
        </div>
    </body>
    </html>
    """
    parser = PageParser(html, "https://example.com/healthcare")
    records, strategy = parser.parse_records()
    assert len(records) == 2
    assert "Strategy B" in strategy
    assert records[0]["title"] == "Daily Contact Lenses 90-Pack"
    assert records[0]["price"] == 65.00
    assert records[1]["title"] == "Company Brand Oxygen Regulator"
    assert records[1]["price"] == 110.00


def test_phase17_14_books_toscrape_product_pod_extraction_succeeds():
    """Verify existing Books-to-Scrape style article.product_pod extraction still succeeds."""
    html = """
    <!DOCTYPE html>
    <html>
    <body>
        <ol class="row">
            <li class="col-xs-6 col-sm-4 col-md-3 col-lg-3">
                <article class="product_pod">
                    <div class="image_container">
                        <a href="catalogue/a-light-in-the-attic_1000/index.html">
                            <img src="media/cache/2c/da/2cdad67c44b002e7ead0cc35693c0e8b.jpg" alt="A Light in the Attic" class="thumbnail">
                        </a>
                    </div>
                    <h3><a href="catalogue/a-light-in-the-attic_1000/index.html" title="A Light in the Attic">A Light in the Attic</a></h3>
                    <div class="product_price">
                        <p class="price_color">£51.77</p>
                        <p class="instock availability"><i class="icon-ok"></i> In stock</p>
                    </div>
                </article>
            </li>
            <li class="col-xs-6 col-sm-4 col-md-3 col-lg-3">
                <article class="product_pod">
                    <div class="image_container">
                        <a href="catalogue/tipping-the-velvet_999/index.html">
                            <img src="media/cache/26/0e/260e9881cceb693324320815b34c6175.jpg" alt="Tipping the Velvet" class="thumbnail">
                        </a>
                    </div>
                    <h3><a href="catalogue/tipping-the-velvet_999/index.html" title="Tipping the Velvet">Tipping the Velvet</a></h3>
                    <div class="product_price">
                        <p class="price_color">£53.74</p>
                        <p class="instock availability"><i class="icon-ok"></i> In stock</p>
                    </div>
                </article>
            </li>
        </ol>
    </body>
    </html>
    """
    parser = PageParser(html, "https://books.toscrape.com/")
    records, strategy = parser.parse_records()
    assert len(records) == 2
    assert "Strategy B" in strategy
    assert records[0]["title"] == "A Light in the Attic"
    assert records[0]["price"] == 51.77
    assert records[0]["currency"] == "GBP"
    assert records[0]["image_url"] == "https://books.toscrape.com/media/cache/2c/da/2cdad67c44b002e7ead0cc35693c0e8b.jpg"
    assert records[1]["title"] == "Tipping the Velvet"
    assert records[1]["price"] == 53.74
    assert records[1]["currency"] == "GBP"
    assert records[1]["image_url"] == "https://books.toscrape.com/media/cache/26/0e/260e9881cceb693324320815b34c6175.jpg"


