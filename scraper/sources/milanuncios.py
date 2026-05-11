                    img_els = card.query_selector_all("img")
                    all_img_urls = []
                    for img_el in img_els:
                        src = img_el.get_attribute("src") or img_el.get_attribute("data-src")
                        if src and src.startswith("http") and "placeholder" not in src.lower():
                            all_img_urls.append(src)

                    loc_el = card.query_selector(".ma-AdLocation-text, [class*='location']")

                    listings.append(CarListing(
                        source="milanuncios",
                        source_id=source_id,
                        title=title,
                        listing_url=url_,
                        price=clean_price(price_el.inner_text()) if price_el else None,
                        year=year,
                        mileage=mileage,
                        fuel=fuel,
                        location=loc_el.inner_text().strip() if loc_el else "Mallorca",
                        image_url=all_img_urls[0] if all_img_urls else None,
                        images=all_img_urls,
                    ))
