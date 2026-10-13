///|
fn finite(x : Double) -> Bool {
  !x.is_nan() && !x.is_inf()
}

///|
fn validate_profile(
  profile : JointProfile,
) -> Result[(Double, Double), JointError] {
  for
    (name, value) in [
      ("bolt_stiffness_n_per_mm", profile.bolt_stiffness_n_per_mm),
      ("joint_stiffness_n_per_mm", profile.joint_stiffness_n_per_mm),
      ("preload_n", profile.preload_n),
      ("stress_area_mm2", profile.stress_area_mm2),
    ] {
    if !finite(value) || value <= 0.0 {
      return Err(InvalidInput("\{name} must be finite and positive"))
    }
  }
  let total = profile.bolt_stiffness_n_per_mm + profile.joint_stiffness_n_per_mm
  let fraction = profile.bolt_stiffness_n_per_mm / total
  // Use kj/total directly: 1-C loses precision for very stiff bolts.
  let clamp_fraction = profile.joint_stiffness_n_per_mm / total
  let separation = profile.preload_n / clamp_fraction
  if !finite(total) ||
    !finite(separation) ||
    fraction <= 0.0 ||
    fraction >= 1.0 ||
    clamp_fraction <= 0.0 {
    return Err(
      InvalidInput("stiffness ratio or separation load cannot be represented"),
    )
  }
  if !finite(profile.preload_n / profile.stress_area_mm2) {
    return Err(InvalidInput("preload stress cannot be represented"))
  }
  Ok((fraction, separation))
}

///|
/// Analyze a nonnegative axial tensile load, strictly before separation.
/// At or above separation, no extrapolated bolt stress is returned.
pub fn analyze_joint(
  profile : JointProfile,
  external_force_n : Double,
) -> Result[JointResult, JointError] {
  let (fraction, separation) = match validate_profile(profile) {
    Ok(value) => value
    Err(error) => return Err(error)
  }
  if !finite(external_force_n) || external_force_n < 0.0 {
    return Err(InvalidInput("external_force_n must be finite and nonnegative"))
  }
  if external_force_n >= separation {
    return Err(SeparationReached(external_force_n, separation))
  }
  let bolt_force = profile.preload_n + fraction * external_force_n
  let clamp_fraction = profile.joint_stiffness_n_per_mm /
    (profile.bolt_stiffness_n_per_mm + profile.joint_stiffness_n_per_mm)
  let clamp_force = profile.preload_n - clamp_fraction * external_force_n
  let stress = bolt_force / profile.stress_area_mm2
  if !finite(bolt_force) || !finite(stress) || clamp_force <= 0.0 {
    return Err(
      InvalidInput("load result cannot be represented within the clamped model"),
    )
  }
  Ok({
    external_force_n,
    load_fraction: fraction,
    bolt_force_n: bolt_force,
    clamp_force_n: clamp_force,
    separation_force_n: separation,
    separation_margin_n: separation - external_force_n,
    stress_mpa: stress,
  })
}

///|
/// Validate the entire input, then convert the valid prefix to stress samples.
/// A separation event stops the history; later loads do not restore validity.
pub fn analyze_load_history(
  profile : JointProfile,
  loads : ArrayView[LoadSample],
) -> Result[HistoryResult, JointError] {
  let (fraction, separation) = match validate_profile(profile) {
    Ok(value) => value
    Err(error) => return Err(error)
  }
  if loads.is_empty() {
    return Err(InvalidInput("load history must contain at least one sample"))
  }
  for i, load in loads {
    if !finite(load.time_s) || !finite(load.force_n) || load.force_n < 0.0 {
      return Err(
        InvalidInput(
          "sample \{i}: time must be finite; force must be finite and nonnegative",
        ),
      )
    }
    if i > 0 && load.time_s <= loads[i - 1].time_s {
      return Err(InvalidInput("sample \{i}: timestamps must strictly increase"))
    }
  }
  let samples : Array[StressSample] = []
  for i, load in loads {
    if load.force_n >= separation {
      return Ok({
        load_fraction: fraction,
        separation_force_n: separation,
        input_samples: loads.length(),
        samples,
        separation: Some({
          sample_index: i,
          time_s: load.time_s,
          force_n: load.force_n,
          separation_force_n: separation,
        }),
      })
    }
    let result = match analyze_joint(profile, load.force_n) {
      Ok(value) => value
      Err(error) => return Err(error)
    }
    samples.push({
      time_s: load.time_s,
      stress_mpa: result.stress_mpa,
      clamp_force_n: result.clamp_force_n,
    })
  }
  Ok({
    load_fraction: fraction,
    separation_force_n: separation,
    input_samples: loads.length(),
    samples,
    separation: None,
  })
}
