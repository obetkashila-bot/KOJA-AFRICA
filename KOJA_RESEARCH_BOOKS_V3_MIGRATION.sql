-- KOJA Research Books V3
-- No new tables are required. V3 uses the existing V2 koja_research_books table.
-- Safe additive index for faster per-user title searches.
create index if not exists koja_research_books_user_title_idx
  on public.koja_research_books(user_id, lower(title));
