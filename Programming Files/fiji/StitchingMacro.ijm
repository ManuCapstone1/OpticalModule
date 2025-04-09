// Get the arguments passed from Python
args = getArgument();
splitArgs = split(args, ",");


grid_size_x = parseInt(splitArgs[0]);
grid_size_y = parseInt(splitArgs[1]);
directory = splitArgs[2];
output_directory = splitArgs[3];
sample_id = splitArgs[4];

print("Starting stitching...");

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

print("Stitching complete.");

print("Loading fused image from disk...");

// Flatten using max intensity projection across Z
run("Z Project...", "projection=[Max Intensity]");

// Save the flattened result
saveAs("JPEG", output_directory + "/stitched_" + sample_id + ".jpg");

print("Saved stitched image.");