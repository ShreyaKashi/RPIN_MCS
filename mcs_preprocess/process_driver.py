import numpy as np
import os
from PIL import Image
from matplotlib import pyplot as plt
import json
import tqdm
import utils as utils
import shutil
import pickle
import cv2

mcs_root_dir = "/home/eris/Desktop/MCS/Dataset/eval5_validation_renamed/eval5_validation_set"
# output_dir = "/home/kashis/Desktop/RPIN/data/MCS_1/"
STORE_PATH="/home/eris/Desktop/MCS/store"
output_dir_SS = "/home/eris/Desktop/MCS/Eval7/out_ss"
MAX_OBJS = 4

def get_obj_entrance_events(seq):
        objEntranceEventList = []

        for obj_id, obj_details in seq.obj_by_id.items():
            if obj_details[0].obj_type == "focused":
                objEntranceEventList.append([obj_id, obj_details[0].frame])

        return objEntranceEventList

def get_obj_exit_events(seq):
        objEntranceEventList = []

        for obj_id, obj_details in seq.obj_by_id.items():
            if obj_details[0].obj_type == "focused":
                objEntranceEventList.append([obj_id, obj_details[-1].frame])

        return objEntranceEventList

def get_reqd_scenes_list():
    scene_list = []
    for scene_name in os.listdir(mcs_root_dir):

        # Get only plaus scenes with no occluders
        if "implaus" in scene_name:
            continue

        folder_path = os.path.join(mcs_root_dir, scene_name)
        rgb_folder = os.path.join(folder_path, "RGB")
        seg_mask = os.path.join(folder_path, "Mask")
        
        step_output_folder = os.path.join(folder_path, "Step_Output")
        step_out_initial = step_output_folder + "/" + os.listdir(step_output_folder)[0]

        with open(step_out_initial) as f:
            step_out_content = json.load(f)
            if any("occluder" in key for key in step_out_content["structural_object_list"]):
                continue

        scene_list.append(scene_name)

    return scene_list
    
def get_step_processed_out(scene_name):
    
    scene_path = f"{mcs_root_dir}/{scene_name}"
    scene_metadata = utils.get_scene_metadata(
        scene_path, scene_name, store_path=STORE_PATH, load=False, save=False
    )
    expected_tracks, vid_len_details = utils.get_tracklets(
        scene_path,
        scene_name,
        store_path=STORE_PATH,
        load=False,
        save=False,
        provide_shape=True,
    )

    seq = utils.get_metadata_from_pipleine(expected_tracks, scene_metadata, vid_len_details)
    states_dict_2 = utils.preprocessing(vid_len_details, seq, scene_metadata)

    return expected_tracks, scene_metadata, seq, states_dict_2   

def get_vid_start_len(seq, states_dict_2):
    # Find start frame no and vid len
    focused_objs = [k for k, v in states_dict_2.items() if v["obj_type"] == "focused"]
    obj_entrance_events = get_obj_entrance_events(seq)
    obj_exit_events = get_obj_exit_events(seq)

    if (len(focused_objs) == 1):
         start_frame = obj_entrance_events[0][1]
         end_frame = obj_exit_events[0][1]
         vid_len_details = (start_frame, end_frame - start_frame)
    else:
         common_entrance_frame = max([frame_no for obj_id, frame_no in obj_entrance_events])
         first_exit_frame = min([frame_no for obj_id, frame_no in obj_exit_events])
         vid_len_details = (common_entrance_frame, first_exit_frame - common_entrance_frame)

    return vid_len_details[0], vid_len_details[1]

def get_max_vid_len(reqd_scenes, recompute=False):
    if (recompute):
        common_vid_len = []
        for scene_name in reqd_scenes:
            expected_tracks, scene_metadata, seq, states_dict_2 = get_step_processed_out(scene_name)
            start_frame, vid_len = get_vid_start_len(seq, states_dict_2)
            common_vid_len.append(vid_len)
        return min(common_vid_len)
 
    else:
        return 34




scene_folder_name_init = '0000'

reqd_scenes = get_reqd_scenes_list()
max_vid_len = get_max_vid_len(reqd_scenes, False)

for scene_name in reqd_scenes:

    scene_folder_path = os.path.join(mcs_root_dir, scene_name)
    rgb_folder = os.path.join(scene_folder_path, "RGB")
    seg_mask = os.path.join(scene_folder_path, "Mask")
    
    expected_tracks, scene_metadata, seq, states_dict_2 = get_step_processed_out(scene_name)
    
    vid_start_frame, vid_len = get_vid_start_len(seq, states_dict_2)

    obj_bbox_list = []
    obj_mask_list = []

    # Trim videos and create a new dir
    for idx, frame_id in enumerate(range(vid_start_frame, vid_start_frame + max_vid_len)):
        src = rgb_folder + "/" + str(frame_id).zfill(6) + ".png"
        dst = output_dir_SS + scene_folder_name_init
        target_file_name = str(idx).zfill(3) + ".png"
        loaded_src_img = cv2.cvtColor(
                       cv2.imread(src),
                       cv2.COLOR_BGR2RGB,
                   )
        
        if not os.path.exists(str(output_dir_SS) + scene_folder_name_init):
           os.makedirs(str(output_dir_SS) + scene_folder_name_init)
        cv2.imwrite(os.path.join(dst, target_file_name), loaded_src_img)


        temp_obj_bbox_dict = []
        temp_obj_mask_list = []
        # Get bbox and mask
        for k, v in states_dict_2.items():
            if v["obj_type"] == "focused":
                bbox_vals = v["2dbbox"][frame_id]
                temp_obj_bbox_dict.append([k, bbox_vals[0], bbox_vals[1], bbox_vals[0] + bbox_vals[2], bbox_vals[1] + bbox_vals[3]])
                seg_color_frame = expected_tracks[k]["content"][frame_id]["segment_color"]
                mask_img = cv2.cvtColor(
                     cv2.imread(f"{scene_folder_path}/Mask/{frame_id:06d}.png"),
                     cv2.COLOR_BGR2RGB,
                 )
                selected_mask = np.logical_and.reduce(
                 (
                     mask_img[:, :, 0] == seg_color_frame["r"],
                     mask_img[:, :, 1] == seg_color_frame["g"],
                     mask_img[:, :, 2] == seg_color_frame["b"],
                 )
                 )
                if np.sum(selected_mask) == 0:
                 continue
                cropped_image = selected_mask[bbox_vals[1]:bbox_vals[1]+bbox_vals[3], bbox_vals[0]:bbox_vals[0]+bbox_vals[2]]
                resized_cropped_img = cv2.resize(cropped_image.astype("float32"), (28, 28))
                temp_obj_mask_list.append(resized_cropped_img)
        obj_bbox_list.append(temp_obj_bbox_dict)
        obj_mask_list.append(temp_obj_mask_list)
    
    obj_bbox_np = np.asarray(obj_bbox_list, dtype=np.float64)
    bbox_dst = output_dir_SS + scene_folder_name_init + "_boxes.pkl"
    pickle.dump(obj_bbox_np, open(bbox_dst, "wb"))

    obj_mask_np = np.asarray(obj_mask_list, dtype=np.float64)
    mask_dst = output_dir_SS + scene_folder_name_init + "_masks.pkl"
    pickle.dump(obj_mask_np, open(mask_dst, "wb"))


             

    # scene_folder_name_init = str(int(scene_folder_name_init) + 1).zfill(4)



