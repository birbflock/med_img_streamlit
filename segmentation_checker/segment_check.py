import re
from turtle import onrelease
import SimpleITK as sitk
import numpy as np
import pandas as pd

from visualization import *
from pathlib import Path
from mnts.utils import get_fnames_by_IDs, get_unique_IDs

import streamlit as st
import pprint
import plotly.express as px

from typing import *

st.set_page_config(layout="wide")  
st.write("# Segmentation Checker")

@st.cache_data
def load_pair(MRI_DIR: Path, SEG_DIR: Path, id_globber:str = r"\w+\d+"):
    # Globbing files
    mri_files, seg_files = MRI_DIR.rglob("*nii.gz"), SEG_DIR.rglob("*nii.gz")
    mri_files = {re.search(id_globber, f.name).group(): f for f in mri_files}
    seg_files = {re.search(id_globber, f.name).group(): f for f in seg_files}

    # Get files with both segmentation and MRI
    intersection = list(set(mri_files.keys()).intersection(seg_files.keys()))
    intersection.sort()

    # Forming pairs
    paired = {sid: (mri_files[sid], seg_files[sid]) for sid in intersection}
    return paired

# This should hold your nii.gz images
if st.session_state.get("require_setup", True):
    st.session_state.mri_dir = Path(st.text_input("<MRI_DIR>:", value="/home/lwong/Storage/Data/NPC_Segmentation/60.Large-Study/v1-All-Data/Normalized_2"))
    # This should hold your nii.gz segmentations
    st.session_state.seg_dir = Path(st.text_input("<SEG_DIR>:", value="/home/lwong/Storage/Data/NPC_Segmentation/60.Large-Study/v1-All-Data/Normalized_2_NPCseg"))
    # This is a regex globber
    st.session_state.id_globber = st.text_input("Regex ID globber:", value=r"\w{0,5}\d+")

# Target ID list
with st.expander("Specify ID"):
    target_ids = st.text_input("CSV string", value="")
    if len(target_ids):
        target_ids = list(set(target_ids.split(',')))

mri_dir = st.session_state.mri_dir
seg_dir = st.session_state.seg_dir
id_globber = st.session_state.id_globber

# Get paired MRI and segmentation
if mri_dir.is_dir() and seg_dir.is_dir():
    paired = load_pair(mri_dir, seg_dir)
    intersection = list(paired.keys())
    intersection.sort()
    # further filtering if target_ids specified
    if len(target_ids):
        intersection = set(intersection) & set(target_ids)
        if missing := set(target_ids) - set(intersection):
            st.warning(f"IDs specified but the following are missing: {','.join(missing)}")
        intersection = list(intersection)
    st.session_state.require_setup = False
else:
    st.error(f"`{str(mri_dir)}` or `{str(seg_dir)}` not found!")
    st.stop()

# Streamlit app
st.title("MRI and segmentation viewer")

# Load Excel file into session state
frame_path = Path("./Checked_Images.csv")
if 'dataframe' not in st.session_state:
    if frame_path.is_file():
        dataframe = pd.read_csv(frame_path)
    else:
        dataframe = pd.DataFrame(columns=["PairID", "Checked", "NeedFix"])
    dataframe['PairID'] = dataframe['PairID'].astype(str)
    st.session_state.dataframe = dataframe
        
# Initialize session state
if 'selection_index' not in st.session_state:
    st.session_state.selection_index = 0

# Selection box
selected_index = st.selectbox("Select a pair", range(len(intersection)), format_func=lambda x: intersection[x], index=st.session_state.selection_index)
st.session_state.selection_index = selected_index
selected_pair = str(intersection[selected_index])

# Function to save DataFrame
def save_dataframe():
    st.session_state.dataframe.to_csv(frame_path, index=False)

def update_dataframe(pair_id, need_fix=False):
    df = st.session_state.dataframe
    if not ((df["PairID"] == pair_id) & (df["Checked"])).any():
        new_row = pd.Series({"PairID": pair_id, "Checked": True, "NeedFix": need_fix})
        st.session_state.dataframe = pd.concat([df, new_row.to_frame().T], ignore_index=True)

@st.dialog("Are you sure?")
def confirm_popup(text="Are you sure?"):
    st.error(text)
    if st.button(":red[Yes]"):
        st.session_state.last_confirmation = 1
        st.rerun()
    if st.button("No"):
        st.session_state.last_confirmation = 0
        st.rerun()

if selected_pair:
    if any(selected_pair == str(x) for x in st.session_state.dataframe['PairID']):
        st.warning("You have already seen this case!")
    
    with st.container(height=700):
        image_slot = st.empty()
    
    # Sliders for window levels
    lower, upper = st.slider(
            'Window Levels',
            min_value=0,
            max_value=99,
            value=(25, 99)
        )

    
    with st.spinner("Running"):
        mri_path, seg_path = paired[selected_pair]

        # Load images
        mri_image = sitk.GetArrayFromImage(sitk.ReadImage(str(mri_path)))
        seg_image = sitk.GetArrayFromImage(sitk.ReadImage(str(seg_path)))

        try:
            mri_image, seg_image = crop_image_to_segmentation(mri_image, seg_image, 20)
        except ValueError:
            st.warning("Something wrong with the segmetnation.")

        # Rescale
        ncols = 5
        mri_image = rescale_intensity(make_grid(mri_image, ncols=ncols), 
                                      lower = lower, 
                                      upper = upper)
        seg_image = make_grid((seg_image != 0), ncols=ncols).astype('int')

        try:
            mri_image = draw_contour(mri_image, seg_image != 0, width=2)
        except ValueError:
            st.warning("Something wrong with the segmetnation.")

        # Display images
        image_slot.image(mri_image, use_column_width=True)

    # Button to go back one option
    col1, col2, col3 = st.columns([1, 1, 3])
    with col1:
        if st.button('⬅️', use_container_width=True):
            current_index = selected_index
            previous_index = (current_index - 1) % len(intersection)
            st.session_state.selection_index = previous_index
            st.rerun()
            # Button to clear the current record
        if st.button("↩️ Clear Current Record", use_container_width=True):
            st.session_state.dataframe = st.session_state.dataframe[st.session_state.dataframe["PairID"] != selected_pair]
            st.rerun()
    
    # Button to load the next option
    with col2:
        if st.button('➡️ Checked and Next', use_container_width=True):
            current_index = selected_index
            update_dataframe(intersection[current_index])
            next_index = (current_index + 1) % len(intersection)
            while str(intersection[next_index]) in st.session_state.dataframe['PairID'].values:
                next_index += 1
            st.session_state.selection_index = next_index
            st.rerun()
        if st.button('➡️ Mark as need fix)', use_container_width=True):
            current_index = selected_index
            update_dataframe(intersection[current_index], True)
            next_index = (current_index + 1) % len(intersection)
            while next_index != current_index:
                next_pair = intersection[next_index]
                if not st.session_state.dataframe.query(f"PairID == '{next_pair}' & Checked == True").empty:
                    next_index = (next_index + 1) % len(intersection)
                else:
                    break
            st.session_state.selection_index = next_index
            st.rerun()

    with col3:
        # Clear button to clear all content of the dataframe
        if st.button(':red[Delete All]'):
            confirm_popup("Are you absolutely sure? You will clear all records!")
            answer = st.session_state.get('last_confirmation', 0)
            if answer:
                st.write("Done")
            # if st.button(":red[Yes]"):
            #     # st.session_state.dataframe = pd.DataFrame(columns=["PairID", "Checked"])
            #     pass
            # if st.button("No"):
            #     pass
            
            

    # Example button to save the DataFrame
    if st.button('Save DataFrame'):
        save_dataframe()
        st.success("DataFrame saved!")

# Progress
st.progress(len(st.session_state.dataframe) / float(len(intersection)), 
            text=f"Progress: ({len(st.session_state.dataframe)} / {len(intersection)})")

# Show dataframe
with st.popover("Data Overview", use_container_width=True):
    st.dataframe(st.session_state.dataframe, use_container_width=True)

    # Show statistics
    # Count the occurrences of each value in the 'NeedFix' column
    need_fix_counts = st.session_state.dataframe['NeedFix'].value_counts()

    # Create a pie chart using Plotly
    fig = px.pie(
        names=need_fix_counts.index,
        values=need_fix_counts.values,
        title="Need Fix Counts"
    )

    # Display the pie chart in Streamlit
    st.plotly_chart(fig)