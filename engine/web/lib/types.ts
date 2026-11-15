// Shapes from docs/API_CONTRACT.md. Every field is treated as optional at
// render time, because the API is built in parallel and may omit fields.

export type Share = { value?: number | null; lo?: number | null; hi?: number | null; n?: number | null };

export type ClaimCard = {
  cid: string;
  claim: string;
  project?: string;
  project_name?: string;
  date?: string;
  channel?: string;
  domain?: string;
  url?: string;
  topic?: string;
  polarity?: string;
  doc_id?: string;
  voice?: string;
  family_id?: string | null;
  family_name?: string | null;
};

export type Match = ClaimCard & {
  relation?: string;
  p_same?: number | null;
  p_related?: number | null;
  cos?: number | null;
  score_source?: string;
};

export type PostCard = {
  doc_id: string;
  date?: string;
  channel?: string;
  media_type?: string;
  domain?: string;
  source_name?: string;
  url?: string;
  lang?: string;
  title?: string;
  excerpt?: string;
  project?: string;
  stance?: string;
  tone?: string;
  passing?: boolean;
  label_source?: string;
  voice?: string;
  dup_count?: number;
  n_claims?: number;
  run_id?: string;
};

export type PostDetail = PostCard & {
  claims?: ClaimCard[];
  classifications?: {
    project?: string;
    stance?: string;
    tone?: string;
    passing?: boolean;
    label_source?: string;
    codebook?: string;
  };
  duplicates?: number;
};

export type EventRef = {
  date?: string;
  title?: string;
  verified?: string | boolean;
  source?: string;
  source_url?: string;
  event_type?: string;
  project?: string;
};

export type CrossCase = {
  claim?: ClaimCard;
  relation?: string;
  p_same?: number | null;
  p_related?: number | null;
  score_source?: string;
  note?: string;
  timeline_available?: boolean;
  stage?: EventRef | null;
  after?: EventRef[];
};

export type Cutoffs = { new?: number; familiar?: number };

export type Concern = {
  concern_id: string;
  state?: string;
  label?: string;
  project?: string;
  first_seen?: string;
  flagged_at?: string | null;
  n_claims?: number;
  n_voices?: number;
  polarity?: Record<string, number>;
  topic?: string;
  project_name?: string;
  uncertainty?: { novelty_score?: number | null; best_older_p_same?: number | null; cutoffs?: Cutoffs; note?: string };
  new_anywhere?: boolean;
  claims?: Match[];
  related_new_claims?: Match[];
  closest_older?: Match[];
  elsewhere?: CrossCase[];
  events_nearby?: EventRef[];
  // "gaining" concerns may carry extra numbers; shown generically if present
  [extra: string]: unknown;
};

export type Health = {
  status?: string;
  data_version?: string;
  n_posts?: number;
  n_claims?: number;
  matcher?: { available?: boolean; mode?: string; version?: string };
  embedder?: { available?: boolean; backend?: string };
  llm?: { backend?: string; available?: boolean };
};

export type ProjectMeta = {
  id: string;
  name?: string;
  has_arguments?: boolean;
  n_posts?: number;
  n_claims?: number;
  first_date?: string;
  last_date?: string;
};

export type Meta = {
  projects?: ProjectMeta[];
  topics?: string[];
  channels?: string[];
  stances?: string[];
  limitations?: string[];
  metrics?: Record<string, unknown>;
  model?: { name?: string; version?: string; trained_until?: string; checksum?: string };
};

export type TopicShare = { topic: string; n?: number; pro?: number; contra?: number; neutral?: number };

export type TopArgument = {
  family_id: string;
  name?: string;
  n?: number;
  pro?: number;
  contra?: number;
  neutral?: number;
  n_voices?: number;
  n_posts?: number;
  by_project?: Record<string, number>;
  main_topic?: string;
  first_seen?: string;
  last_seen?: string;
};

export type PeriodRow = {
  month?: string;
  period?: string;
  n?: number;
  support?: number;
  oppose?: number;
  neutral?: number;
  mixed?: number;
};

export type Overview = {
  n_posts?: number;
  n_unique_posts?: number;
  n_voices?: number;
  n_with_stance?: number;
  stance_counts?: Record<string, number>;
  opposition_share?: Share;
  channel_counts?: Record<string, number>;
  top_sources?: { domain: string; n: number }[];
  topic_shares?: TopicShare[];
  top_arguments?: TopArgument[];
  monthly?: PeriodRow[];
  notes?: string[];
};

export type Trends = {
  series?: PeriodRow[];
  peaks?: { period?: string; n?: number; expected?: number; p_value?: number; headline?: string; event?: string | EventRef | null }[];
  events?: EventRef[];
  notes?: string[];
};

export type PostsList = { total?: number; items?: PostCard[] };

export type FamiliesList = { items?: TopArgument[]; notes?: string[]; has_arguments?: boolean };
export type FamilyDetail = TopArgument & { claims?: ClaimCard[]; notes?: string[] };

export type ClaimDetail = {
  claim?: ClaimCard;
  post?: PostCard;
  equivalent?: Match[];
  related?: Match[];
  elsewhere?: CrossCase[];
  mode?: string;
  note?: string;
};

export type SearchResult = { mode?: string; matcher_mode?: string; results?: Match[] };

export type MatchResult = {
  novelty?: { state?: string; score?: number | null; best_p_same?: number | null; cutoffs?: Cutoffs; note?: string };
  matches?: Match[];
  elsewhere?: CrossCase[];
  mode?: string;
};

export type EmergingResult = { cutoff?: string; mode?: string; model_version?: string; concerns?: Concern[]; counts?: Record<string, number>; notes?: string[] };

export type ReplayStep = {
  i?: number;
  ts?: string;
  claim?: ClaimCard;
  decision?: string;
  matched?: Match | null;
  concern_id?: string | null;
  raised?: string[];
  novelty_score?: number | null;
};

export type Replay = {
  project?: string;
  cutoff?: string;
  mode?: string;
  model_version?: string;
  simulation?: boolean;
  label?: string;
  thresholds?: Cutoffs & Record<string, number | undefined>;
  counts?: Record<string, number>;
  known_before?: { n_claims?: number; n_posts?: number; top_families?: { family_id: string; name?: string; n?: number }[] };
  steps?: ReplayStep[];
  concerns?: Concern[];
  activity?: { week?: string; n?: number; new?: number; familiar?: number; ambiguous?: number }[];
};

export type ReplayCutoffs = { cutoffs?: string[]; earliest_allowed?: string; reason?: string };

export type LiveCheck = {
  available?: boolean;
  cached?: { cand?: string; p_same?: number }[];
  live?: { cand?: string; p_same?: number }[];
  max_abs_diff?: number | null;
  message?: string;
  reason?: string;
};

export type CrossCityProject = {
  id: string;
  name?: string;
  n_posts?: number;
  n_with_stance?: number;
  opposition_share?: Share;
  topic_shares?: TopicShare[];
};

export type CrossCity = {
  projects?: CrossCityProject[];
  shared_arguments?: TopArgument[];
  notes?: string[];
};

export type SimilarResult = { cases?: CrossCase[]; mode?: string; note?: string; novelty?: { state?: string; note?: string } };

export type RunStep = { name?: string; status?: string; n_in?: number; n_out?: number; secs?: number; message?: string };

export type Run = {
  run_id: string;
  filename?: string;
  sha256?: string;
  created_at?: string;
  status?: string;
  steps?: RunStep[];
  counts?: Record<string, number>;
  errors?: { record?: string | number; step?: string; message?: string }[];
  findings?: { concerns?: Concern[] };
  models?: Record<string, string>;
};

export type RunsList = { runs?: Run[] };
