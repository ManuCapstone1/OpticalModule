// Get the arguments passed from Python
args = getArgument();
splitArgs = split(args, ",");

grid_size_x = parseInt(splitArgs[0]);
grid_size_y = parseInt(splitArgs[1]);
directory = splitArgs[2];
output_directory = splitArgs[3];
sample_id = splitArgs[4];

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
  "compute_overlap subpixel_accuracy " +
  "computation_parameters=[Save computation time (but use more RAM)] " +
  "image_output=[Fuse and display]");

File.append("2. Stitching plugin finished without crashing.\n", log_path);

// FIX: Convert the 32-bit blended result to RGB before saving as JPEG.
// Linear Blending produces a 32-bit float image; JPEG requires 8-bit RGB.
// Skipping this step causes saveAs to silently abort with no error.
run("RGB Color");
File.append("3. Image successfully converted to RGB.\n", log_path);

save_path = output_directory + File.separator + "stitched_" + sample_id + ".jpg";
File.append("4. Attempting to save to: " + save_path + "\n", log_path);

saveAs("Jpeg", save_path);
File.append("5. Save complete! Initiating graceful shutdown.\n", log_path);

close("*");
eval("script", "System.exit(0);");
