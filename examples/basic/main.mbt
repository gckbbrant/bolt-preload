///|
fn main {
  let profile : @joint.JointProfile = {
    bolt_stiffness_n_per_mm: 200000.0,
    joint_stiffness_n_per_mm: 800000.0,
    preload_n: 10000.0,
    stress_area_mm2: 50.0,
  }
  let result = @joint.analyze_joint(profile, 5000.0).unwrap()
  println("Bolt force: \{result.bolt_force_n} N")
  println("Clamp force: \{result.clamp_force_n} N")
  println("Nominal bolt stress: \{result.stress_mpa} MPa")
}
