// Get the arguments passed from Python
args = getArgument();
splitArgs = split(args, ",");

grid_size_x = parseInt(splitArgs[0]);
grid_size_y = parseInt(splitArgs[1]);
directory = splitArgs[2];
output_directory = splitArgs[3];
sample_id = splitArgs[4];
compute_overlap = parseInt(splitArgs[5]);

// ImageJ checkbox params are a bare keyword when checked, omitted when not
overlap_flag = "";
if (compute_overlap == 1) {
  overlap_flag = "compute_overlap ";
}

// Setup the Flight Recorder Log
log_path = output_directory + File.separator + "fiji_log.txt";
File.saveString("--- FIJI STITCHING LOG ---\n", log_path);
File.append("1. Arguments received successfully.\n", log_path);

run("Grid/Collection stitching",
  "type=[Grid: column-by-column] " +
  "order=[Up & Right] " +
  "grid_size_x=" + grid_size_x + " " +
  "grid_size_y=" + grid_size_y + " " +
  "tile_overlap=20 first_file_index_i=0 " +
  "directory=[" + directory + "] " +
  "file_names={i}_" + sample_id + ".jpg " +
  "output_textfile_name=TileConfiguration.txt " +
  "fusion_method=[Linear Blending] " +
  "regression_threshold=0.30 " +
  "max/avg_displacement_threshold=2.50 " +
  "absolute_displacement_threshold=3.50 " +
  overlap_flag + "subpixel_accuracy " +
  "computation_parameters=[Save computation time (but use more RAM)] " +
  "image_output=[Fuse and display]");

File.append("2. Stitching plugin finished without crashing.\n", log_path);

// Convert the blended result to RGB before saving as JPEG (JPEG requires
// 8-bit RGB; skipping this entirely causes saveAs to silently abort with no
// error). With COLOR tile inputs, Grid/Collection Stitching's Linear
// Blending fusion typically outputs each of R/G/B as a separate slice in a
// multi-channel stack, not a single merged color image. "RGB Color" only
// converts whichever ONE slice is currently active into R=G=B -- a real
// channel, but colorized as grey -- which is why the saved JPEG was
// technically RGB but looked black-and-white. "Stack to RGB" is the command
// that actually merges the 3 channel slices into true color; fall back to
// "RGB Color" only if this run's fused result isn't a stack at all.
// Logged so a still-grey result can be diagnosed from fiji_log.txt alone
// (was it a stack that got merged, or did it fall to the single-slice path?)
File.append("2b. nSlices after fusion = " + nSlices + "\n", log_path);
if (nSlices > 1) {
  run("Stack to RGB");
  File.append("2c. Took Stack to RGB path.\n", log_path);
} else {
  run("RGB Color");
  File.append("2c. Took RGB Color (single-slice) path.\n", log_path);
}
File.append("3. Image successfully converted to RGB.\n", log_path);

save_path = output_directory + File.separator + "stitched_" + sample_id + ".jpg";
File.append("4. Attempting to save to: " + save_path + "\n", log_path);

saveAs("Jpeg", save_path);
File.append("5. Save complete! Initiating graceful shutdown.\n", log_path);

close("*");
eval("script", "System.exit(0);");
