///|
/// Draw the pre-separation force model with labelled axes in N.
pub fn render_svg(profile : JointProfile) -> Result[String, JointError] {
  let (fraction, separation) = match validate_profile(profile) {
    Ok(value) => value
    Err(error) => return Err(error)
  }
  let top_force = profile.preload_n + fraction * separation
  if !finite(top_force) {
    return Err(InvalidInput("plot scale cannot be represented"))
  }
  let preload_y = 310.0 - 245.0 * profile.preload_n / top_force
  let output = StringBuilder()
  output.write_string(
    "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 780 410\" role=\"img\" aria-labelledby=\"title desc\">\n",
  )
  output.write_string(
    "<title id=\"title\">Preloaded bolt force distribution</title><desc id=\"desc\">Axial linear model, only before separation. Force in newtons.</desc>\n",
  )
  output.write_string(
    "<rect width=\"780\" height=\"410\" fill=\"#f7f8fa\"/><g font-family=\"sans-serif\" fill=\"#263449\">\n",
  )
  output.write_string(
    "<text x=\"60\" y=\"32\" font-size=\"22\">bolt-preload · axial joint</text><text x=\"60\" y=\"53\" font-size=\"12\">C = \{fraction}; preload = \{profile.preload_n} N</text>\n",
  )
  output.write_string(
    "<path d=\"M70 65V310H680\" fill=\"none\" stroke=\"#758299\"/><path d=\"M70 \{preload_y} L650 65\" fill=\"none\" stroke=\"#2563eb\" stroke-width=\"3\"/><path d=\"M70 \{preload_y} L650 310\" fill=\"none\" stroke=\"#15803d\" stroke-width=\"3\"/>\n",
  )
  output.write_string(
    "<path d=\"M650 65V310\" stroke=\"#c2410c\" stroke-dasharray=\"5 4\"/><text x=\"75\" y=\"83\" font-size=\"13\">Bolt force (N)</text><text x=\"110\" y=\"269\" fill=\"#15803d\" font-size=\"13\">Remaining clamp force (N)</text>\n",
  )
  output.write_string(
    "<text x=\"70\" y=\"330\" font-size=\"12\">0</text><text x=\"440\" y=\"348\" font-size=\"13\">Separation: \{separation} N</text><text x=\"250\" y=\"369\" font-size=\"13\">External tensile force (N)</text><text x=\"60\" y=\"394\" font-size=\"12\">At separation the clamped model stops; this chart does not extrapolate bolt stress.</text>\n",
  )
  output.write_string("</g></svg>\n")
  Ok(output.to_string())
}
