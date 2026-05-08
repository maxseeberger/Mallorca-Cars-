-- Run this in your Supabase SQL editor once

create table if not exists listings (
  id          uuid primary key default gen_random_uuid(),
  source_id   text not null,          -- original ID from source site
  source      text not null,          -- 'wallapop' | 'milanuncios' | 'coches_net'
  title       text not null,
  price       integer,                -- in euros, null if "on request"
  year        integer,
  mileage     integer,                -- km
  fuel        text,                   -- 'diesel' | 'gasoline' | 'hybrid' | 'electric'
  gearbox     text,                   -- 'manual' | 'automatic'
  make        text,                   -- 'BMW', 'VW', etc.
  model       text,
  location    text,
  image_url   text,
  listing_url text not null,
  description text,
  is_featured boolean default false,  -- paid dealer featured slot
  is_active   boolean default true,
  first_seen  timestamptz default now(),
  last_seen   timestamptz default now(),
  unique (source, source_id)
);

-- Index for common filter queries
create index if not exists idx_listings_active   on listings (is_active, last_seen desc);
create index if not exists idx_listings_price    on listings (price) where is_active;
create index if not exists idx_listings_make     on listings (make)  where is_active;
create index if not exists idx_listings_year     on listings (year)  where is_active;

-- Mark stale listings (not seen in last 3 days) as inactive
-- Call this after each scrape run via Supabase function or from Python
create or replace function deactivate_stale_listings()
returns void language sql as $$
  update listings
  set is_active = false
  where last_seen < now() - interval '3 days'
    and is_active = true;
$$;

-- Dealers table for paid featured listings
create table if not exists dealers (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  phone       text,
  whatsapp    text,
  website     text,
  plan        text default 'featured',  -- 'featured' | 'premium'
  active_until date,
  created_at  timestamptz default now()
);
