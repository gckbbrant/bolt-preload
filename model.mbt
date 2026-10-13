///|
/// Stiffnesses in N/mm, preload in N, effective tensile area in mm².
pub(all) struct JointProfile {
  bolt_stiffness_n_per_mm : Double
  joint_stiffness_n_per_mm : Double
  preload_n : Double
  stress_area_mm2 : Double
} derive(Eq, Debug, ToJson, FromJson)

///|
pub(all) enum JointError {
  InvalidInput(String)
  SeparationReached(Double, Double)
} derive(Eq, Debug, ToJson)

///|
/// Only valid before separation. MPa equals N/mm².
pub(all) struct JointResult {
  external_force_n : Double
  load_fraction : Double
  bolt_force_n : Double
  clamp_force_n : Double
  separation_force_n : Double
  separation_margin_n : Double
  stress_mpa : Double
} derive(Debug, ToJson)

///|
pub extend JointProfile with Eq::{equal, not_equal}

///|
pub extend JointProfile with @debug.Debug::{to_repr}

///|
pub extend JointProfile with ToJson::{to_json}

///|
pub extend JointProfile with @json.FromJson::{from_json}

///|
pub extend JointError with Eq::{equal, not_equal}

///|
pub extend JointError with @debug.Debug::{to_repr}

///|
pub extend JointError with ToJson::{to_json}

///|
pub extend JointResult with @debug.Debug::{to_repr}

///|
pub extend JointResult with ToJson::{to_json}

///|
pub extend LoadSample with @debug.Debug::{to_repr}

///|
pub extend LoadSample with ToJson::{to_json}

///|
pub extend LoadSample with @json.FromJson::{from_json}

///|
pub extend StressSample with @debug.Debug::{to_repr}

///|
pub extend StressSample with ToJson::{to_json}

///|
pub extend Separation with @debug.Debug::{to_repr}

///|
pub extend Separation with ToJson::{to_json}

///|
pub extend HistoryResult with @debug.Debug::{to_repr}

///|
pub extend HistoryResult with ToJson::{to_json}

///|
pub(all) struct LoadSample {
  time_s : Double
  force_n : Double
} derive(Debug, ToJson, FromJson)

///|
pub(all) struct StressSample {
  time_s : Double
  stress_mpa : Double
  clamp_force_n : Double
} derive(Debug, ToJson)

///|
pub(all) struct Separation {
  sample_index : Int
  time_s : Double
  force_n : Double
  separation_force_n : Double
} derive(Debug, ToJson)

///|
/// Contains only the valid prefix if separation is reached.
pub(all) struct HistoryResult {
  load_fraction : Double
  separation_force_n : Double
  input_samples : Int
  samples : Array[StressSample]
  separation : Separation?
} derive(Debug, ToJson)
