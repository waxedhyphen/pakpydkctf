import anim_track_skel_map_patch as m

def install(App):
    def valid_groups(probe,groups):
        frame_count=probe.get('frame_count_guess') or 0
        if not frame_count:
            return [],'missing_frame_count'
        usable=[]
        for group in groups:
            if group.get('mapping_mode','')=='unmapped_count_mismatch':
                continue
            frames=m._timeline_frame_count(group)
            if frames>0:
                group['timeline_frame_count']=frames
                usable.append(group)
        if not usable:
            return [],'no_usable_groups'
        total=sum(group.get('timeline_frame_count') or 0 for group in usable)
        if total==frame_count:
            return usable,'ok:sequential_groups'
        exact=[group for group in usable if (group.get('timeline_frame_count') or 0)==frame_count]
        if exact:
            return exact,'ok:single_full_group'
        if probe.get('track_decode',{}).get('status')=='ok:fallback_raw_blocks':
            return usable,'ok:fallback_groups'
        return [],f'frame_coverage_mismatch:{total}!={frame_count}'
    m._valid_groups=valid_groups
