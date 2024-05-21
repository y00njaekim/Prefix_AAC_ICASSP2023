import random
import torch
from torch.utils.data import Dataset
from torch.utils.data import DataLoader
import pandas as pd
import torchaudio
import os
import numpy as np
from tqdm import tqdm
import pickle
import re
from torch.utils.data import SubsetRandomSampler
import string


def fix_caption(caption) :
    caption = caption.lower()
                    
    caption = caption.replace(',', ' , ') 

    caption = re.sub(' +', ' ', caption)
    caption = caption.replace(' ,', ',')
             
    caption = re.sub(r'[.]', '', caption)
                
    caption += '.'
                   
    caption = caption.strip()
    
    return caption
    

class FusionDataset(Dataset):
    
    def compress_audio(self, audio, set_length = 10) :
        
        ratio = audio.size()[0]/(self.SAMPLE_RATE * set_length)
        
        compress_idx_list = []
        
        for idx in range(self.SAMPLE_RATE * set_length) :
            compress_idx_list.append(int(ratio * idx))

        return audio[compress_idx_list]
    
    def __init__(self, tokenizer, split, prefix_size) :  # split = 'train' or 'test'
        super(FusionDataset, self).__init__()
        
        self.SAMPLE_RATE = 16000
        self.split = split
        
        self.audiocaps_dir = './AudioCaps/'
        self.clotho_dir = './Clotho/'
        
        if split == 'train' :
            audiocaps_csv_file = pd.read_csv(self.audiocaps_dir + 'train/train.csv')
            clotho_csv_file    = pd.read_csv(self.clotho_dir + 'clotho_csv_files/clotho_captions_development.csv')
            
            audiocaps_full_path_prefix = './AudioCaps/train/'
            
            audiocaps_audio_file_list = os.listdir(self.audiocaps_dir + 'train')
            clotho_audio_file_list = os.listdir(self.clotho_dir + 'clotho_audio_files/development')
            
            clotho_full_path_prefix = './Clotho/clotho_audio_files/development/'
            
        else :
            audiocaps_csv_file = pd.read_csv(self.audiocaps_dir + 'test/test.csv')
            clotho_csv_file    = pd.read_csv(self.clotho_dir + 'clotho_csv_files/clotho_captions_evaluation.csv')
            
            audiocaps_full_path_prefix = './AudioCaps/test/'
            
            audiocaps_audio_file_list = os.listdir(self.audiocaps_dir + 'test')
            clotho_audio_file_list = os.listdir(self.clotho_dir + 'clotho_audio_files/evaluation')
            
            clotho_full_path_prefix = './Clotho/clotho_audio_files/evaluation/'
        
        self.path_list = []
        self.file_name_list = []
        self.token_list = []
        self.caption_list_for_test = []
                     
        
        for file in tqdm(clotho_audio_file_list, desc = 'get dataset from clotho...') :
            
            audio_full_path = clotho_full_path_prefix + file
            
            for i in range(5) :
                self.path_list.append(audio_full_path)
                self.file_name_list.append(file)
                
                sentence_str = 'caption_' + str(i + 1)
                
                caption = clotho_csv_file[clotho_csv_file['file_name'] == file][sentence_str].item()
        
                caption = fix_caption(caption)
                
                if split != 'train' :
                    self.caption_list_for_test.append(caption)
                else :
                    tokens = tokenizer(caption)['input_ids']
                    self.token_list.append(torch.tensor(tokens))
                    
        for file in tqdm(audiocaps_audio_file_list, desc = 'get dataset from audiocaps...') :
            if file[-3:] == 'wav' :
                file_row_in_csv = audiocaps_csv_file[audiocaps_csv_file['youtube_id'] == file[:-4]]
                
                captions = file_row_in_csv['caption'].to_list() 
                for caption in captions :
                    
                    self.path_list.append(audiocaps_full_path_prefix + file)
                    self.file_name_list.append(file)
                    
                    caption = fix_caption(caption)
                    
                    if split != 'train' :
                        self.caption_list_for_test.append(caption)
                    else :
                        tokens = tokenizer(caption)['input_ids']
                        self.token_list.append(torch.tensor(tokens))
            
        
        if split == 'train' :          
            self.all_len = torch.tensor([len(self.token_list[i]) for i in range(len(self.token_list))]).float()
            self.max_seq_len = min(int(self.all_len.mean() + self.all_len.std() * 10), int(self.all_len.max()))
        self.prefix_length = prefix_size # audio_prefix_length + semantic_prefix_length
            
    def __len__(self):
       
        return len(self.path_list)
    
    def pad_tokens(self, item: int):
        tokens = self.token_list[item].clone().detach()
        padding = self.max_seq_len - tokens.shape[0]
        if padding > 0:
            tokens = torch.cat((tokens, torch.zeros(padding, dtype=torch.int64) - 1))
            self.token_list[item] = tokens
        elif padding < 0:
            tokens = tokens[:self.max_seq_len]
            self.token_list[item] = tokens
        mask = tokens.ge(0)  # mask is zero where we out of sequence
        tokens[~mask] = 0
        mask = mask.float()
        mask = torch.cat((torch.ones(self.prefix_length), mask), dim=0)  # adding prefix mask
        return tokens, mask
    
    
    def __getitem__(self, item: int) :
        
        audio_file, _ = torchaudio.load(self.path_list[item])
        audio_file = audio_file[0,:] 

        set_length = 10
        
        if 'AudioCaps' in self.path_list[item] :
            # slicing
            if audio_file.size()[0] > (self.SAMPLE_RATE * set_length) :
                audio_file = audio_file[:self.SAMPLE_RATE * set_length]
            # zero padding
            if audio_file.size()[0] < (self.SAMPLE_RATE * set_length) :
                pad_len = (self.SAMPLE_RATE * set_length) - audio_file.shape[0]
                pad_val = torch.zeros(pad_len)
                audio_file = torch.cat((audio_file, pad_val), dim=0)
        else :
            audio_file = self.compress_audio(audio_file)
        
        if self.split == 'train' :
            tokens, mask = self.pad_tokens(item)
            return audio_file, tokens, mask, self.file_name_list[item]
        else :
            return audio_file, self.caption_list_for_test[item], self.file_name_list[item]
            



def dataloader_FusionDataset(tokenizer, batch_size, split, prefix_size, is_TrainDataset=False, subset_ratio=1.0):
    dataset = FusionDataset(tokenizer, split, prefix_size)

    cpu_core_num = 8
    
    # 데이터셋의 일부만 선택하기 위한 인덱스 생성
    dataset_size = len(dataset)
    subset_size = int(dataset_size * subset_ratio)
    subset_indices = random.sample(range(dataset_size), subset_size)
    
    if is_TrainDataset:
        sampler = SubsetRandomSampler(subset_indices)
        is_shuffle = True
        is_drop_last = True
    else:
        sampler = None
        is_shuffle = False
        is_drop_last = False
    
    
    dataloader = DataLoader(dataset=dataset,
                            batch_size=batch_size,
                            shuffle=is_shuffle,
                            num_workers=cpu_core_num,
                            drop_last=is_drop_last,
                            sampler=sampler)
    
    return dataloader