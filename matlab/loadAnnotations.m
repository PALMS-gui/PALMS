function [data] = loadAnnotations(fn)
  data = [];
  info = h5info(fn);
  %%%%%%%%%%%%% META %%%%%%%%%%%%%%%%%%%%%%%%
  meta = [];
  if ismember('/meta',{info.Groups.Name})
    idx = find(cell2mat(arrayfun(@(x) ((strcmpi(x.Name,'/meta'))),info.Groups,'un',0)));
    m  = {info.Groups(idx).Datasets.Name};
    for i=1:numel(m)
      meta.(m{i}) = h5read(fn,['/meta/',m{i}]);
    end
  end
  
  %%%%%%%%%%%%% TRACKS %%%%%%%%%%%%%%%%%%%%%%%%
  signals = [];
  if ismember('/tracks',{info.Groups.Name})
    
    idx = find(cell2mat(arrayfun(@(x) ((strcmpi(x.Name,'/tracks'))),info.Groups,'un',0)));
    tracks  = info.Groups(idx).Groups;
    
    for i=1:numel(tracks)
      id = strsplit(tracks(i).Name,'/');
      signals.(id{end}).ts = h5read(fn,['/tracks/',id{end},'/ts']);
      signals.(id{end}).amp = h5read(fn,['/tracks/',id{end},'/amp']);
      signals.(id{end}).fs = h5read(fn,['/tracks/',id{end},'/fs']);
      signals.(id{end}).offset = h5read(fn,['/tracks/',id{end},'/offset']);
    end
  end
  %%%%%%%%%%%%% ANNOTATION MODE %%%%%%%%%%%%%%%%%%%%%%%%
  ann = [];
  if ismember('/annotations',{info.Groups.Name})
    
    idx = find(cell2mat(arrayfun(@(x) ((strcmpi(x.Name,'/annotations'))),info.Groups,'un',0)));
    annotations = info.Groups(idx).Groups;
    
    for i=1:numel(annotations)
      id = strsplit(annotations(i).Name,'/');
      ann.(id{end}).ts = h5read(fn,['/annotations/',id{end},'/ts']);
      ann.(id{end}).amp = h5read(fn,['/annotations/',id{end},'/amp']);
      ann.(id{end}).idx = h5read(fn,['/annotations/',id{end},'/idx']);
    end
  end
  %%%%%%%%%%%%% PARTITION MODE %%%%%%%%%%%%%%%%%%%%%%%%
  part = [];
  if ismember('/partitions',{info.Groups.Name})
    idx = find(cell2mat(arrayfun(@(x) ((strcmpi(x.Name,'/partitions'))),info.Groups,'un',0)));
    partitions = info.Groups(idx);
    
    part.start_ts = h5read(fn,['/partitions/start']);
    part.end_ts = h5read(fn,['/partitions/end']);
    part.label = h5read(fn,['/partitions/label']);
    if ~isempty(part.label)
      part.label = cellfun(@(x) strip(strrep(x,char(0),'')),part.label,'un',0);
    end
    if ~isempty(part)
      part = struct2table(part);
    end
  end
  %%%%%%%%%%%%% EPOCH MODE %%%%%%%%%%%%%%%%%%%%%%%%
  ep = [];
  if ismember('/epoch',{info.Groups.Name})
    all_labels = h5read(fn,'/epoch/all_labels');
    all_labels = cellfun(@(x) strip(strrep(x,char(0),'')),all_labels,'un',0);
    default_label = h5read(fn,'/epoch/default_label');
    NONE_LABEL = h5read(fn,'/epoch/NONE_LABEL');
    all_descriptions = h5read(fn,'/epoch/description');
    
    label = h5read(fn,'/epoch/label');
    label = cellfun(@(x) strip(strrep(x,char(0),'')),label,'un',0);
    start_ts = h5read(fn,'/epoch/start');
    end_ts = h5read(fn,'/epoch/end');
    is_modified = h5read(fn,'/epoch/is_modified');
    
    label_idx = cell2mat(cellfun(@(x) find(strcmpi(strip(x),strip(all_labels))),label,'un',0));
    description = all_descriptions(label_idx);
    
    
    data.start_ts = start_ts;
    data.end_ts = end_ts;
    data.label = label;
    data.is_modified = is_modified;
    data.label_idx = label_idx;
    data.description = description;
    % data = struct2table(data,'AsArray',true);
    
    
    ep.meta.all_labels = all_labels;
    ep.meta.all_descriptions = all_descriptions;
    ep.meta.default_label = default_label;
    ep.meta.none_labels = NONE_LABEL;
    ep.data = data;
  end
  %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
  data = [];
  data.meta = meta;
  data.signals = signals;
  data.annotations = ann;
  data.partitions = part;
  data.epochs = ep;
  
end