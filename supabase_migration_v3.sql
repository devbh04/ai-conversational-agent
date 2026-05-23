-- ══════════════════════════════════════════════════════════════════════════════
-- SUPABASE MIGRATION v3 — Real Estate Fields
-- Run this in your Supabase SQL Editor
-- ══════════════════════════════════════════════════════════════════════════════

-- Add columns to store property requirements and site visit timing
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS property_preferences TEXT;
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS site_visit_time      TEXT;

-- We can drop 'was_booked' if we want, but it's safe to keep it as a boolean 
-- indicator that a site visit was requested.
