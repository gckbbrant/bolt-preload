///|
fn profile() -> @app.JointProfile {
  {
    bolt_stiffness_n_per_mm: 200000.0,
    joint_stiffness_n_per_mm: 800000.0,
    preload_n: 10000.0,
    stress_area_mm2: 50.0,
  }
}

///|
test "hand calculation and force balance" {
  let result = @app.analyze_joint(profile(), 5000.0).unwrap()
  assert_true(result.load_fraction.is_close(0.2))
  assert_true(result.bolt_force_n.is_close(11000.0))
  assert_true(result.clamp_force_n.is_close(6000.0))
  assert_true(result.stress_mpa.is_close(220.0))
  assert_true(result.separation_force_n.is_close(12500.0))
  assert_true((result.bolt_force_n - result.clamp_force_n).is_close(5000.0))
}

///|
test "zero external load preserves preload" {
  let result = @app.analyze_joint(profile(), 0.0).unwrap()
  assert_eq(result.bolt_force_n, 10000.0)
  assert_eq(result.clamp_force_n, 10000.0)
  assert_eq(result.stress_mpa, 200.0)
}

///|
test "separation threshold is outside the clamped model" {
  assert_true(@app.analyze_joint(profile(), 12499.0) is Ok(_))
  assert_true(
    @app.analyze_joint(profile(), 12500.0) is Err(@app.SeparationReached(_, _)),
  )
  assert_true(
    @app.analyze_joint(profile(), 13000.0) is Err(@app.SeparationReached(_, _)),
  )
}

///|
test "history preserves valid prefix and does not resume after separation" {
  let history = @app.analyze_load_history(profile(), [
    { time_s: 0.0, force_n: 0.0, },
    { time_s: 1.0, force_n: 5000.0, },
    { time_s: 2.0, force_n: 12500.0, },
    { time_s: 3.0, force_n: 0.0, },
  ]).unwrap()
  assert_eq(history.samples.length(), 2)
  assert_true(history.separation is Some({ sample_index: 2, .. }))
}

///|
test "reject invalid forces, parameters, timestamps and hidden bad rows" {
  assert_true(@app.analyze_joint(profile(), -1.0) is Err(@app.InvalidInput(_)))
  assert_true(
    @app.analyze_joint(profile(), 0.0 / 0.0) is Err(@app.InvalidInput(_)),
  )
  assert_true(
    @app.analyze_joint({ ..profile(), stress_area_mm2: 0.0, }, 0.0)
    is Err(@app.InvalidInput(_)),
  )
  assert_true(
    @app.analyze_joint({ ..profile(), preload_n: 1.0 / 0.0, }, 0.0)
    is Err(@app.InvalidInput(_)),
  )
  assert_true(
    @app.analyze_load_history(profile(), []) is Err(@app.InvalidInput(_)),
  )
  assert_true(
    @app.analyze_load_history(profile(), [
      { time_s: 0.0, force_n: 1.0, },
      { time_s: 0.0, force_n: 2.0, },
    ])
    is Err(@app.InvalidInput(_)),
  )
  assert_true(
    @app.analyze_load_history(profile(), [
      { time_s: 0.0, force_n: 13000.0, },
      { time_s: 1.0, force_n: -1.0, },
    ])
    is Err(@app.InvalidInput(_)),
  )
}

///|
test "stiffness changes load amplitude while preload changes mean stress" {
  let stiff_joint = profile()
  let soft_joint = { ..stiff_joint, joint_stiffness_n_per_mm: 300000.0, }
  let a = @app.analyze_joint(stiff_joint, 5000.0).unwrap()
  let b = @app.analyze_joint(soft_joint, 5000.0).unwrap()
  assert_true(b.stress_mpa > a.stress_mpa)
  let high_preload = @app.analyze_joint(
    { ..stiff_joint, preload_n: 12000.0, },
    5000.0,
  ).unwrap()
  assert_true((high_preload.stress_mpa - a.stress_mpa).is_close(40.0))
  assert_eq(high_preload.load_fraction, a.load_fraction)
}
